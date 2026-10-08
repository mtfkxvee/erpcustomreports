"""
Livechat AI - X-SHA ERPNext
=============================
Backend tool-calling ke OpenRouter. Config diambil dari DocType "Livechat
AI Settings". Tiap chat (sukses/gagal, plus biaya USD dari OpenRouter)
dicatat ke "Livechat AI Log" - lihat report "Livechat AI Usage Dashboard".

Endpoint: /api/method/custom_reports.api.livechat.chat

Semua query ke database pakai parametrized SQL (%(param)s), tidak ada raw
SQL dari input user - aman dari SQL injection.
"""

import json
import time

import frappe
import requests
from frappe.utils import today

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

DEFAULT_MODEL = "openai/gpt-5.6-luna"
DEFAULT_MAX_TOOL_ROUNDTRIPS = 5
DEFAULT_ALLOWED_ROLES = {"System Manager", "Purchase Manager", "Purchase User", "Stock Manager", "Accounts Manager"}
DEFAULT_AI_NAME = "X-SHA Livechat AI"
DEFAULT_SYSTEM_PROMPT = (
	"Kamu adalah asisten AI internal untuk staff ERPNext PT. Meta Global Triasha (X-SHA), "
	"retail chain FMCG & Fashion multi-outlet di Tasikmalaya, Jawa Barat. "
	"Jawab dalam Bahasa Indonesia, singkat, langsung ke angka/fakta. "
	"Kalau butuh data spesifik, WAJIB panggil tool yang tersedia - jangan pernah mengarang angka."
)
DEFAULT_WELCOME_MESSAGE = (
	"Halo! Aku asisten AI ERP X-SHA. Bisa nanya soal omzet, stock, status PO, atau service level supplier."
)

TOOLS = [
	{
		"type": "function",
		"function": {
			"name": "get_sales_summary",
			"description": "Total omzet (grand_total, exclude retur) dan jumlah struk dari Sales Invoice, untuk 1 outlet atau semua outlet, dalam rentang tanggal.",
			"parameters": {
				"type": "object",
				"properties": {
					"outlet_code": {"type": "string", "description": "Kode custom_outlet, misal 'XSM'. Kosongkan untuk semua outlet."},
					"date_from": {"type": "string", "description": "Format YYYY-MM-DD"},
					"date_to": {"type": "string", "description": "Format YYYY-MM-DD"},
				},
				"required": ["date_from", "date_to"],
			},
		},
	},
	{
		"type": "function",
		"function": {
			"name": "get_stock_balance",
			"description": "Cari stock balance (actual_qty) suatu item, di 1 warehouse atau semua warehouse. Bisa pakai item_code persis atau kata kunci nama item. Kalau nggak ketemu, hasil berisi 'suggestions' - item lain yang namanya mirip.",
			"parameters": {
				"type": "object",
				"properties": {
					"item_search": {"type": "string", "description": "item_code persis, atau kata kunci nama item"},
					"warehouse": {"type": "string", "description": "nama warehouse persis, misal 'GUDANG DC - X'. Kosongkan untuk semua warehouse."},
				},
				"required": ["item_search"],
			},
		},
	},
	{
		"type": "function",
		"function": {
			"name": "get_po_status",
			"description": "Cek status Purchase Order: per_received (%), per_billed (%), grand_total, status. Bisa cari by nomor PO persis, atau by nama supplier + rentang tanggal (list beberapa PO terakhir).",
			"parameters": {
				"type": "object",
				"properties": {
					"po_name": {"type": "string", "description": "Nomor PO persis, misal 'PUR-ORD-2026-00014'"},
					"supplier_search": {"type": "string", "description": "Kata kunci nama supplier"},
					"date_from": {"type": "string"},
					"date_to": {"type": "string"},
				},
			},
		},
	},
	{
		"type": "function",
		"function": {
			"name": "get_service_level",
			"description": "Hitung service level (total PO vs total RCV yang link ke PO itu, %fulfillment) per supplier atau per item group, dalam rentang tanggal, untuk scope warehouse FMCG atau FASHION.",
			"parameters": {
				"type": "object",
				"properties": {
					"date_from": {"type": "string"},
					"date_to": {"type": "string"},
					"warehouse_root": {"type": "string", "enum": ["FMCG - X", "FASHION - X"], "description": "Default 'FMCG - X'"},
					"group_by": {"type": "string", "enum": ["Supplier", "Item Group"], "description": "Default 'Supplier'"},
				},
				"required": ["date_from", "date_to"],
			},
		},
	},
]


def _get_settings():
	try:
		return frappe.get_cached_doc("Livechat AI Settings")
	except frappe.DoesNotExistError:
		return None


def _allowed_roles(settings):
	if settings and settings.allowed_roles:
		roles = {r.strip() for r in settings.allowed_roles.splitlines() if r.strip()}
		if roles:
			return roles
	return DEFAULT_ALLOWED_ROLES


def _check_access(settings):
	if frappe.session.user == "Guest":
		frappe.throw("Silakan login dulu", frappe.PermissionError)
	user_roles = set(frappe.get_roles(frappe.session.user))
	if not (user_roles & _allowed_roles(settings)):
		frappe.throw("Kamu tidak punya akses ke Livechat AI ini", frappe.PermissionError)


def _passcode_configured(settings):
	if not settings:
		return False
	try:
		pw = settings.get_password("passcode", raise_exception=False)
	except Exception:
		pw = None
	return bool(pw)


def _unlock_cache_key():
	return f"xsha_livechat_unlocked::{frappe.session.user}"


def _is_unlocked(settings):
	if not _passcode_configured(settings):
		return True
	return bool(frappe.cache().get_value(_unlock_cache_key()))


@frappe.whitelist()
def unlock(passcode):
	settings = _get_settings()
	if not _passcode_configured(settings):
		return {"ok": True}
	correct = settings.get_password("passcode")
	if passcode and passcode == correct:
		frappe.cache().set_value(_unlock_cache_key(), 1, expires_in_sec=8 * 3600)
		return {"ok": True}
	return {"ok": False}


@frappe.whitelist()
def get_widget_config():
	"""Dipanggil widget JS saat load - nentuin bubble muncul, nama AI, welcome message, dan passcode gate."""
	if frappe.session.user == "Guest":
		return {"enabled": False}
	settings = _get_settings()
	is_enabled = bool(settings.enabled) if settings else True
	user_roles = set(frappe.get_roles(frappe.session.user))
	has_access = bool(user_roles & _allowed_roles(settings))
	welcome = (settings.welcome_message if settings and settings.welcome_message else DEFAULT_WELCOME_MESSAGE)
	ai_name = (settings.ai_name if settings and settings.ai_name else DEFAULT_AI_NAME)
	return {
		"enabled": is_enabled and has_access,
		"welcome_message": welcome,
		"ai_name": ai_name,
		"passcode_required": not _is_unlocked(settings),
	}


def _get_fmcg_warehouses(root):
	r = frappe.db.get_value("Warehouse", root, ["lft", "rgt"], as_dict=True)
	if not r:
		return [root]
	rows = frappe.db.sql(
		"""
		select name from `tabWarehouse`
		where lft > %(lft)s and rgt < %(rgt)s and is_group = 0
		""",
		{"lft": r.lft, "rgt": r.rgt},
		as_dict=True,
	)
	return [x.name for x in rows] or [root]


def _tool_get_sales_summary(date_from, date_to, outlet_code=None):
	conditions = ["docstatus = 1", "posting_date between %(date_from)s and %(date_to)s", "is_return = 0"]
	params = {"date_from": date_from, "date_to": date_to}
	if outlet_code:
		conditions.append("custom_outlet = %(outlet_code)s")
		params["outlet_code"] = outlet_code
	where = " and ".join(conditions)
	row = frappe.db.sql(
		f"""
		select count(name) as total_trx, sum(grand_total) as total_omzet
		from `tabSales Invoice`
		where {where}
		""",
		params,
		as_dict=True,
	)[0]
	return {
		"outlet": outlet_code or "ALL",
		"period": f"{date_from} s/d {date_to}",
		"total_transaksi": row.total_trx or 0,
		"total_omzet": float(row.total_omzet or 0),
	}


def _suggest_items(item_search):
	words = [w for w in item_search.split() if len(w) >= 3]
	if not words:
		return []
	conditions = " or ".join([f"item_name like %(w{i})s" for i in range(len(words))])
	params = {f"w{i}": f"%{w}%" for i, w in enumerate(words)}
	return frappe.db.sql(
		f"""
		select item_code, item_name
		from `tabItem`
		where ({conditions}) and disabled = 0
		limit 8
		""",
		params,
		as_dict=True,
	)


def _tool_get_stock_balance(item_search, warehouse=None):
	params = {"search": f"%{item_search}%", "code": item_search}
	where = "(b.item_code = %(code)s or i.item_name like %(search)s)"
	if warehouse:
		where += " and b.warehouse = %(warehouse)s"
		params["warehouse"] = warehouse
	rows = frappe.db.sql(
		f"""
		select b.item_code, i.item_name, b.warehouse, b.actual_qty, b.stock_uom
		from `tabBin` b
		join `tabItem` i on i.name = b.item_code
		where {where} and b.actual_qty != 0
		order by b.actual_qty desc
		limit 20
		""",
		params,
		as_dict=True,
	)
	if rows:
		return {"results": rows, "count": len(rows)}

	suggestions = _suggest_items(item_search)
	return {
		"results": [],
		"count": 0,
		"suggestions": suggestions,
		"message": "Item tidak ditemukan persis. Cek field 'suggestions' buat item yang namanya mirip.",
	}


def _tool_get_po_status(po_name=None, supplier_search=None, date_from=None, date_to=None):
	if po_name:
		doc = frappe.db.get_value(
			"Purchase Order",
			po_name,
			["supplier_name", "transaction_date", "grand_total", "per_received", "per_billed", "status"],
			as_dict=True,
		)
		return doc or {"error": f"PO {po_name} tidak ditemukan"}

	conditions = ["docstatus = 1"]
	params = {}
	if supplier_search:
		conditions.append("supplier_name like %(supplier)s")
		params["supplier"] = f"%{supplier_search}%"
	if date_from and date_to:
		conditions.append("transaction_date between %(date_from)s and %(date_to)s")
		params["date_from"] = date_from
		params["date_to"] = date_to
	where = " and ".join(conditions)
	rows = frappe.db.sql(
		f"""
		select name, supplier_name, transaction_date, grand_total, per_received, per_billed, status
		from `tabPurchase Order`
		where {where}
		order by transaction_date desc
		limit 20
		""",
		params,
		as_dict=True,
	)
	return {"results": rows, "count": len(rows)}


def _tool_get_service_level(date_from, date_to, warehouse_root="FMCG - X", group_by="Supplier"):
	warehouses = _get_fmcg_warehouses(warehouse_root)
	params = {"date_from": date_from, "date_to": date_to, "warehouses": warehouses}

	if group_by == "Item Group":
		po_rows = frappe.db.sql(
			"""
			select poi.item_group as key_, sum(poi.base_amount) as po_amount
			from `tabPurchase Order Item` poi
			join `tabPurchase Order` po on po.name = poi.parent
			where po.docstatus = 1 and po.transaction_date between %(date_from)s and %(date_to)s
			  and poi.warehouse in %(warehouses)s
			group by poi.item_group
			""",
			params,
			as_dict=True,
		)
		rcv_rows = frappe.db.sql(
			"""
			select pri.item_group as key_, sum(pri.base_amount) as rcv_amount
			from `tabPurchase Receipt Item` pri
			join `tabPurchase Receipt` pr on pr.name = pri.parent
			join `tabPurchase Order` po on po.name = pri.purchase_order
			where pr.docstatus = 1 and pr.is_return = 0
			  and po.transaction_date between %(date_from)s and %(date_to)s
			  and pri.warehouse in %(warehouses)s
			group by pri.item_group
			""",
			params,
			as_dict=True,
		)
	else:
		po_rows = frappe.db.sql(
			"""
			select po.supplier as key_, sum(poi.base_amount) as po_amount
			from `tabPurchase Order Item` poi
			join `tabPurchase Order` po on po.name = poi.parent
			where po.docstatus = 1 and po.transaction_date between %(date_from)s and %(date_to)s
			  and poi.warehouse in %(warehouses)s
			group by po.supplier
			""",
			params,
			as_dict=True,
		)
		rcv_rows = frappe.db.sql(
			"""
			select po.supplier as key_, sum(pri.base_amount) as rcv_amount
			from `tabPurchase Receipt Item` pri
			join `tabPurchase Receipt` pr on pr.name = pri.parent
			join `tabPurchase Order` po on po.name = pri.purchase_order
			where pr.docstatus = 1 and pr.is_return = 0
			  and po.transaction_date between %(date_from)s and %(date_to)s
			  and pri.warehouse in %(warehouses)s
			group by po.supplier
			""",
			params,
			as_dict=True,
		)

	rcv_map = {r.key_: (r.rcv_amount or 0) for r in rcv_rows}
	results = []
	for r in po_rows:
		po_amt = r.po_amount or 0
		rcv_amt = rcv_map.get(r.key_, 0)
		servel = (rcv_amt / po_amt * 100) if po_amt else 0
		results.append({"key": r.key_, "po_amount": po_amt, "rcv_amount": rcv_amt, "servel_pct": round(servel, 1)})
	results.sort(key=lambda x: x["po_amount"], reverse=True)
	return {"group_by": group_by, "period": f"{date_from} s/d {date_to}", "results": results[:20]}


TOOL_FUNCS = {
	"get_sales_summary": _tool_get_sales_summary,
	"get_stock_balance": _tool_get_stock_balance,
	"get_po_status": _tool_get_po_status,
	"get_service_level": _tool_get_service_level,
}


def _date_context():
	current_date = today()
	current_year = current_date.split("-")[0]
	return (
		f"\n\n[KONTEKS TANGGAL] Hari ini tanggal {current_date} (tahun {current_year}). "
		"Kalau user pakai kata relatif seperti 'hari ini', 'kemarin', 'minggu ini', 'bulan ini', "
		"langsung hitung sendiri tanggal absolutnya (format YYYY-MM-DD) dari referensi ini - "
		"JANGAN tanya balik ke user. Kalau user cuma sebut nama bulan tanpa tahun (misal "
		f"'Agustus'), pakai tahun {current_year} kecuali user sebut tahun lain secara eksplisit."
	)


def _log_chat(message, reply, tools_called, success, error_message, model, start_time, cost_usd=0):
	try:
		frappe.get_doc(
			{
				"doctype": "Livechat AI Log",
				"user": frappe.session.user,
				"message": (message or "")[:1900],
				"reply": reply or "",
				"success": 1 if success else 0,
				"error_message": (error_message or "")[:1900],
				"response_time_ms": int((time.time() - start_time) * 1000),
				"tools_called": ",".join(tools_called) if tools_called else "",
				"model": model,
				"cost_usd": cost_usd or 0,
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()
	except Exception:
		frappe.log_error(title="Livechat AI: gagal simpan log")


@frappe.whitelist()
def chat(message, history=None):
	# 2026-09-20: provider dialihkan ke OpenCode Zen (saldo OpenRouter habis). Widget lama yang masih tersimpan
	# di cache browser (max-age 1 tahun) tetap memanggil endpoint ini -> teruskan ke modul baru.
	# Kode di bawah ini tidak dipakai lagi (dibiarkan supaya rollback = pulihkan file dari backup).
	from custom_reports.api.livechat_opencode import chat as _chat_opencode

	return _chat_opencode(message, history)

	settings = _get_settings()
	start_time = time.time()
	model = (settings.model if settings and settings.model else DEFAULT_MODEL)

	if settings and not settings.enabled:
		frappe.throw("Livechat AI sedang dinonaktifkan oleh admin")

	_check_access(settings)

	if not _is_unlocked(settings):
		frappe.throw("Passcode belum diverifikasi. Refresh halaman dan masukkan passcode dulu.", frappe.PermissionError)

	api_key = frappe.conf.get("openrouter_api_key")
	if not api_key:
		frappe.throw("openrouter_api_key belum diset di site_config.json")

	system_prompt = (settings.system_prompt if settings and settings.system_prompt else DEFAULT_SYSTEM_PROMPT)
	system_prompt = system_prompt + _date_context()
	max_roundtrips = (settings.max_tool_roundtrips if settings and settings.max_tool_roundtrips else DEFAULT_MAX_TOOL_ROUNDTRIPS)

	if isinstance(history, str):
		history = json.loads(history)
	history = history or []

	messages = [{"role": "system", "content": system_prompt}] + history + [{"role": "user", "content": message}]
	tools_called = []
	total_cost = 0.0

	try:
		for _ in range(int(max_roundtrips)):
			resp = requests.post(
				OPENROUTER_URL,
				headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
				json={
					"model": model,
					"messages": messages,
					"tools": TOOLS,
					"tool_choice": "auto",
					"usage": {"include": True},
				},
				timeout=30,
			)
			resp.raise_for_status()
			result = resp.json()
			usage = result.get("usage") or {}
			total_cost = total_cost + (usage.get("cost") or 0)
			msg = result["choices"][0]["message"]
			messages.append(msg)

			tool_calls = msg.get("tool_calls")
			if not tool_calls:
				reply = msg.get("content", "")
				_log_chat(message, reply, tools_called, True, None, model, start_time, total_cost)
				return {"reply": reply, "history": messages[1:]}

			for tc in tool_calls:
				fn_name = tc["function"]["name"]
				tools_called.append(fn_name)
				try:
					args = json.loads(tc["function"]["arguments"] or "{}")
				except Exception:
					args = {}
				fn = TOOL_FUNCS.get(fn_name)
				try:
					tool_result = fn(**args) if fn else {"error": f"tool {fn_name} tidak dikenal"}
				except Exception as e:
					tool_result = {"error": str(e)}
				messages.append(
					{
						"role": "tool",
						"tool_call_id": tc["id"],
						"content": json.dumps(tool_result, default=str),
					}
				)

		reply = "Maaf, terlalu banyak langkah untuk jawab ini. Coba pertanyaan yang lebih spesifik."
		_log_chat(message, reply, tools_called, True, None, model, start_time, total_cost)
		return {"reply": reply, "history": messages[1:]}

	except Exception as e:
		_log_chat(message, None, tools_called, False, str(e), model, start_time, total_cost)
		raise
