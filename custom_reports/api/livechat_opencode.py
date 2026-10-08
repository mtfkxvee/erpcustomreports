"""
Livechat AI - X-SHA ERPNext - varian OpenCode Zen
==================================================
Endpoint: /api/method/custom_reports.api.livechat_opencode.chat

Sama persis dengan custom_reports.api.livechat.chat (alat/tools, akses role, passcode, log, dashboard
tetap dipakai dari modul lama), bedanya hanya provider model: OpenCode Zen lewat API /responses
(https://opencode.ai/docs/zen/), bukan OpenRouter /chat/completions.

- Kunci API: site_config.json -> "opencode_api_key" (JANGAN ditulis di kode/git/docs).
- Nama model diambil dari DocType "Livechat AI Settings" seperti biasa; awalan "openai/" (gaya OpenRouter)
  otomatis dibuang -> "openai/gpt-5.6-luna" menjadi "gpt-5.6-luna".
- Format riwayat chat ke/dari browser TETAP format chat/completions (system/user/assistant/tool), supaya widget
  dan riwayat di sessionStorage tidak perlu diubah. Konversi ke format /responses hanya terjadi di sini.
- Biaya (Cost USD di dashboard) dihitung dari jumlah token x tabel harga PRICES (OpenCode tidak mengirim biaya).

Modul lama (livechat.py) TIDAK diubah -> rollback = arahkan widget kembali ke custom_reports.api.livechat.chat.
"""

import json
import time

import frappe
import requests

from custom_reports.api.livechat import (
	DEFAULT_MAX_TOOL_ROUNDTRIPS,
	DEFAULT_MODEL,
	DEFAULT_SYSTEM_PROMPT,
	TOOL_FUNCS,
	TOOLS,
	_check_access,
	_date_context,
	_get_settings,
	_is_unlocked,
	_log_chat,
)

OPENCODE_URL = "https://opencode.ai/zen/v1/responses"
REQUEST_TIMEOUT = 60

# USD per 1 juta token, dari https://opencode.ai/docs/zen/ (tarif <= 272K token per permintaan).
# Model yang tidak ada di sini dicatat biayanya 0 (chat tetap jalan). Cek harga terbaru kalau ganti model.
PRICES = {
	"gpt-5.6-luna": {"in": 0.20, "cached": 0.02, "out": 1.20},
}


def _opencode_model(model):
	"""'openai/gpt-5.6-luna' -> 'gpt-5.6-luna' (OpenCode memakai ID tanpa awalan provider)."""
	return (model or DEFAULT_MODEL).split("/")[-1]


def _responses_tools():
	"""TOOLS (format chat/completions, dibungkus 'function') -> format /responses (datar)."""
	return [
		{
			"type": "function",
			"name": t["function"]["name"],
			"description": t["function"].get("description", ""),
			"parameters": t["function"].get("parameters", {"type": "object", "properties": {}}),
		}
		for t in TOOLS
	]


def _to_input(messages):
	"""Riwayat format chat/completions -> daftar 'input' untuk /responses. System prompt dikirim lewat
	'instructions', jadi baris system dilewati di sini."""
	items = []
	for m in messages:
		role = m.get("role")
		if role == "user":
			items.append({"role": "user", "content": m.get("content") or ""})
		elif role == "assistant":
			if m.get("content"):
				items.append({"role": "assistant", "content": m["content"]})
			for tc in m.get("tool_calls") or []:
				items.append(
					{
						"type": "function_call",
						"call_id": tc["id"],
						"name": tc["function"]["name"],
						"arguments": tc["function"].get("arguments") or "{}",
					}
				)
		elif role == "tool":
			items.append(
				{"type": "function_call_output", "call_id": m["tool_call_id"], "output": m.get("content") or ""}
			)
	return items


def _from_output(result):
	"""Respons /responses -> satu pesan assistant format chat/completions (content + tool_calls)."""
	texts, calls = [], []
	for item in result.get("output") or []:
		kind = item.get("type")
		if kind == "message":
			for part in item.get("content") or []:
				if part.get("type") in ("output_text", "text"):
					texts.append(part.get("text") or "")
		elif kind == "function_call":
			calls.append(
				{
					"id": item.get("call_id") or item.get("id"),
					"type": "function",
					"function": {"name": item.get("name"), "arguments": item.get("arguments") or "{}"},
				}
			)
	msg = {"role": "assistant", "content": "".join(texts)}
	if calls:
		msg["tool_calls"] = calls
	return msg


def _cost_usd(model, usage):
	price = PRICES.get(model)
	if not price or not usage:
		return 0.0
	tokens_in = usage.get("input_tokens") or 0
	cached = (usage.get("input_tokens_details") or {}).get("cached_tokens") or 0
	tokens_out = usage.get("output_tokens") or 0
	return ((tokens_in - cached) * price["in"] + cached * price["cached"] + tokens_out * price["out"]) / 1e6


def _call_model(api_key, model, instructions, messages):
	resp = requests.post(
		OPENCODE_URL,
		headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
		json={
			"model": model,
			"instructions": instructions,
			"input": _to_input(messages),
			"tools": _responses_tools(),
			"tool_choice": "auto",
			"store": False,
		},
		timeout=REQUEST_TIMEOUT,
	)
	if resp.status_code >= 400:
		raise Exception(f"OpenCode {resp.status_code}: {resp.text[:300]}")
	result = resp.json()
	if result.get("error"):
		raise Exception(f"OpenCode error: {json.dumps(result['error'])[:300]}")
	return result


def _run_chat(api_key, model, system_prompt, history, message, max_roundtrips):
	"""Loop tool-calling. Mengembalikan (reply, messages_tanpa_system, tools_called, total_cost)."""
	messages = [{"role": "system", "content": system_prompt}] + history + [{"role": "user", "content": message}]
	tools_called = []
	total_cost = 0.0

	for _ in range(int(max_roundtrips)):
		result = _call_model(api_key, model, system_prompt, messages)
		total_cost += _cost_usd(model, result.get("usage"))
		msg = _from_output(result)
		messages.append(msg)

		tool_calls = msg.get("tool_calls")
		if not tool_calls:
			return msg.get("content", ""), messages[1:], tools_called, total_cost

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
				{"role": "tool", "tool_call_id": tc["id"], "content": json.dumps(tool_result, default=str)}
			)

	return (
		"Maaf, terlalu banyak langkah untuk jawab ini. Coba pertanyaan yang lebih spesifik.",
		messages[1:],
		tools_called,
		total_cost,
	)


@frappe.whitelist()
def chat(message, history=None):
	settings = _get_settings()
	start_time = time.time()
	model = _opencode_model(settings.model if settings and settings.model else DEFAULT_MODEL)

	if settings and not settings.enabled:
		frappe.throw("Livechat AI sedang dinonaktifkan oleh admin")

	_check_access(settings)

	if not _is_unlocked(settings):
		frappe.throw("Passcode belum diverifikasi. Refresh halaman dan masukkan passcode dulu.", frappe.PermissionError)

	api_key = frappe.conf.get("opencode_api_key")
	if not api_key:
		frappe.throw("opencode_api_key belum diset di site_config.json")

	system_prompt = settings.system_prompt if settings and settings.system_prompt else DEFAULT_SYSTEM_PROMPT
	system_prompt = system_prompt + _date_context()
	max_roundtrips = (
		settings.max_tool_roundtrips if settings and settings.max_tool_roundtrips else DEFAULT_MAX_TOOL_ROUNDTRIPS
	)

	if isinstance(history, str):
		history = json.loads(history)
	history = history or []

	tools_called = []
	total_cost = 0.0
	try:
		reply, new_history, tools_called, total_cost = _run_chat(
			api_key, model, system_prompt, history, message, max_roundtrips
		)
		_log_chat(message, reply, tools_called, True, None, model, start_time, total_cost)
		return {"reply": reply, "history": new_history}
	except Exception as e:
		_log_chat(message, None, tools_called, False, str(e), model, start_time, total_cost)
		raise


def selftest(pertanyaan="Berapa total omzet semua outlet kemarin? Jawab singkat."):
	"""Uji dari command line tanpa browser & tanpa menulis log:
	bench --site erp.x-sha.id execute custom_reports.api.livechat_opencode.selftest
	Memanggil model sungguhan, termasuk 1 putaran tool (baca database, hanya SELECT)."""
	settings = _get_settings()
	api_key = frappe.conf.get("opencode_api_key")
	if not api_key:
		print("GAGAL: opencode_api_key belum diset di site_config.json")
		return
	model = _opencode_model(settings.model if settings and settings.model else DEFAULT_MODEL)
	system_prompt = (
		settings.system_prompt if settings and settings.system_prompt else DEFAULT_SYSTEM_PROMPT
	) + _date_context()
	t0 = time.time()
	reply, hist, tools_called, cost = _run_chat(api_key, model, system_prompt, [], pertanyaan, 5)
	print("model        :", model)
	print("tool dipanggil:", tools_called)
	print("biaya (USD)  :", round(cost, 6))
	print("waktu        :", round(time.time() - t0, 1), "detik")
	print("jawaban      :", reply)
