# Copyright (c) 2026, X-SHA and contributors
# For license information, please see license.txt
#
# Laporan "Monthly Inventory Target vs Inventory Akhir" - tampilan ERP dari file admin "INV TARGET
# VS INV AKHIR AGT26 / SEP26" sheet "EXC KMT, MBG, XSL" (EXC TOPUP; susunan
# baris spt file):
#   TARGET INV  = doctype "Outlet Inventory Target" (input per nama bulan)
#   INV PLUS    = jumlah saldo akhir (Rp) item yg POSITIF di outlet itu
#   INV MINS    = jumlah saldo akhir (Rp) item yg MINUS (stok minus)
#   TOTAL INV   = INV PLUS + INV MINS (= saldo akhir outlet, sama dgn Daily
#                 Inventory varian EXC TOPUP)
#   VS TARGET   = TOTAL INV - TARGET, PERSENTASE = TOTAL INV / TARGET
# File: pivot "Sum of Saldo Akhir (Rp)" dari laporan stok per item per outlet,
# dipisah item plus & minus. Di sini saldo per item dijumlah dulu per OUTLET
# (gudang + selling area + transit), baru dipisah plus/minus.
# Saldo akhir bulan = saldo sekarang (tabBin, actual_qty 0 = 0 spt Daily
# Inventory) - mutasi setelah akhir bulan (Stock Ledger Entry). Query sengaja
# TANPA "IN (daftar warehouse)" & tanpa JOIN tabItem (lihat catatan performa
# di inventory_api): pemetaan warehouse->outlet & buang TOPUP dikerjakan di
# Python. Bulan berjalan = s/d hari ini.

import calendar
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import getdate, today

from custom_reports.inventory_api import (
    _BULAN_ID_INV,
    _excluded_items,
    _inv_target_by_outlet,
    _outlet_warehouses,
    _rupiah,
)

_FASHION_OFFLINE = [("XSC", "Cikiray"), ("PSR", "Pasar"), ("XPY", "Panyingkiran"), ("XJB", "Furniture"),
                    ("XCW", "Ciawi"), ("XSP", "SP Fashion"), ("HCW", "X-sha Rumah Kedua")]
_FASHION_ONLINE = [("XSC-OL", "Online Cikiray"), ("OCW", "Online Ciawi"), ("XSP-OL", "Online SP Fashion")]
_FMCG = [("XSM", "Supermart"), ("XMJ", "X-Shamart Mangunreja"), ("XWP", "X-Shamart Warung Peuteuy"),
         ("XPH", "X-Shamart Puspahiang"), ("XTJ", "X-Shamart Tanjung jaya"), ("XCR", "X-Shamart Cisaruni"),
         ("TASMU", "Tasmu Mart"), ("MNR", "Menara X-Shamart"), ("UIN", "X-sha Grow UIN")]
_GUDANG_FHS = ("GD", "Gudang FHS")


def _plus_minus(as_of_date, outlets):
    """{outlet: {"plus", "minus"}} saldo akhir per item per outlet di as_of_date, EXC TOPUP."""
    wh_to_outlet = {wh: o for o, whs in _outlet_warehouses().items() if o in outlets for wh in whs}
    topup = set(_excluded_items(["TOPUP"]))
    bal = defaultdict(float)
    for r in frappe.db.sql("SELECT warehouse, item_code, stock_value FROM `tabBin` WHERE actual_qty != 0", as_dict=True):
        o = wh_to_outlet.get(r.warehouse)
        if o and r.item_code not in topup:
            bal[(o, r.item_code)] += r.stock_value or 0
    for r in frappe.db.sql("""
        SELECT warehouse, item_code, SUM(stock_value_difference) AS val
        FROM `tabStock Ledger Entry`
        WHERE is_cancelled = 0 AND posting_date > %s
        GROUP BY warehouse, item_code
    """, (as_of_date,), as_dict=True):
        o = wh_to_outlet.get(r.warehouse)
        if o and r.item_code not in topup:
            bal[(o, r.item_code)] -= r.val or 0
    out = {o: {"plus": 0.0, "minus": 0.0} for o in outlets}
    for (o, _item), v in bal.items():
        v = round(v, 2)  # buang noise float
        if v > 0:
            out[o]["plus"] += v
        elif v < 0:
            out[o]["minus"] += v
    return out


def execute(filters=None):
    filters = filters or {}
    now = getdate(today())
    month = _BULAN_ID_INV.index(filters.get("bulan")) + 1 if filters.get("bulan") in _BULAN_ID_INV else now.month
    year = int(filters.get("tahun") or now.year)
    if (year, month) == (now.year, now.month):
        as_of = now
    else:
        as_of = getdate(f"{year}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}")
    if as_of > now:
        frappe.throw(_("Bulan tsb belum terjadi"))

    codes = [c for c, _l in _FASHION_OFFLINE + _FASHION_ONLINE + _FMCG] + [_GUDANG_FHS[0]]
    pm = _plus_minus(as_of, codes)
    targets = _inv_target_by_outlet(_BULAN_ID_INV[month - 1])

    def row(label, cs, bold=0):
        target = sum(targets.get(c) or 0 for c in cs) if any(targets.get(c) is not None for c in cs) else None
        plus = sum(pm[c]["plus"] for c in cs)
        minus = sum(pm[c]["minus"] for c in cs)
        total = plus + minus
        return {"outlet": label, "bold": bold, "target": target, "plus": _rupiah(plus), "minus": _rupiah(minus),
                "total": _rupiah(total), "vs_target": _rupiah(total - target) if target is not None else None,
                "pct": round(total / target * 100, 2) if target else None}

    off, onl, fm = [c for c, _l in _FASHION_OFFLINE], [c for c, _l in _FASHION_ONLINE], [c for c, _l in _FMCG]
    fhs = off + onl + [_GUDANG_FHS[0]]
    data = [row(label, [c]) for c, label in _FASHION_OFFLINE]
    data.append(row("Total Outlet - Offline", off, bold=1))
    data += [row(label, [c]) for c, label in _FASHION_ONLINE]
    data.append(row("Total Outlet - Online", onl, bold=1))
    data.append(row(_GUDANG_FHS[1], [_GUDANG_FHS[0]]))
    data.append(row("DEPT. FHS", fhs, bold=1))
    data += [row(label, [c]) for c, label in _FMCG]
    data.append(row("DEPT.FMCG", fm, bold=1))
    data.append({})
    data.append(row("HO", fhs + fm, bold=1))

    missing = [label for c, label in _FASHION_OFFLINE + _FASHION_ONLINE + _FMCG + [_GUDANG_FHS] if targets.get(c) is None]
    info = f"EXC TOPUP  |  saldo akhir per {as_of.strftime('%d-%m-%Y')}  |  EXC KMT, MBG, XSL"
    if missing:
        info += f"  |  target {_BULAN_ID_INV[month - 1]} blm diinput: {', '.join(missing)}"
    data.insert(0, {"outlet": info, "bold": 1, "is_info": 1})
    return get_columns(), data


def get_columns():
    def col(fieldname, label, fieldtype="Currency", width=150):
        return {"fieldname": fieldname, "label": label, "fieldtype": fieldtype, "width": width}
    return [
        col("outlet", _("OUTLET"), "Data", 220),
        col("target", _("TARGET INV")), col("plus", _("INV PLUS")), col("minus", _("INV MINS")),
        col("total", _("TOTAL INV")), col("vs_target", _("VS TARGET")), col("pct", _("PERSENTASE"), "Percent", 110),
    ]
