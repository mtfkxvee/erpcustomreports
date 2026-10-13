# Copyright (c) 2026, X-SHA and contributors
# For license information, please see license.txt
#
# Laporan "Weekly Sales Achievement (Net Retur & Potongan)" - tampilan ERP dari
# file "WEEKLY MARGIN CLEAR 5-11 OCT" Sheet4 "SALES & MARGIN ACHIEVEMENT"
# kolom Penjualan s.d. SALES - RETUR (susunan baris mengikuti file), ditambah
# Sales Net minggu lalu & growth (dari API). Rumus = API
# sales_api.get_weekly_sales_net_achievement (_margin_row): Sales Net = Penjualan
# - Member - Potongan - Promo - Rafaksi - Retur. Minggu = Senin-Minggu.
# Jurnal potongan dibaca dari snapshot harian (sales_snapshot.load_margin) kalau
# lengkap, kalau tidak live + label "(live)". MBG & Kemitraan = sales input
# manual (Kemitraan MBG Sales History), tanpa potongan - sama spt file.

import frappe
from frappe import _
from frappe.utils import add_days, formatdate, getdate, today

from custom_reports.custom_reports.report.weekly_margin.weekly_margin import _kmt_mbg_sales_hpp
from custom_reports.sales_api import (
    _GL_MARGIN_ACCOUNTS,
    _OUTLET_COST_CENTER,
    _gl_deductions_by_outlet,
    _margin_row,
    _monday_week_bounds,
)
from custom_reports.sales_snapshot import load_margin

_FASHION_OFFLINE = [("XSC", "Cikiray", 1), ("PSR", "Pasar", 2), ("XPY", "Panyingkiran", 3), ("XJB", "Furniture", 4),
                    ("XCW", "Ciawi", 5), ("XSP", "SP Fashion", 6), ("HCW", "Ciawi Home Supplies", 7)]
_FASHION_ONLINE = [("XSC-OL", "Online Cikiray", None), ("OCW", "Online Ciawi", None), ("XSP-OL", "Online SP Fashion", None)]
_FMCG = [("XSM", "Supermart", 1), ("XMJ", "X-Shamart Mangunreja", 2), ("XWP", "X-Shamart Warung Peuteuy", 3),
         ("XPH", "X-Shamart Puspahiang", 4), ("XTJ", "X-Shamart Tanjung jaya", 5), ("XCR", "X-Shamart Cisaruni", 6),
         ("TASMU", "Tasmu Mart", 7), ("MNR", "Menara", 8), ("UIN", "X-sha Grow UIN", 9), ("XSMGROW", "X-sha Grow SP", 10)]
_KEYS = ("sales_bruto", "member", "potongan_penjualan", "promo", "rafaksi_discount", "sales_bruto_2", "retur_penjualan", "sales_retur")


def _week_data(start, end):
    """(gl_data, manual, is_live) utk 1 minggu."""
    snap = load_margin(start, end)
    if snap is None:
        gl = _gl_deductions_by_outlet(start, end, list(_OUTLET_COST_CENTER))
    else:
        gl = snap[0]
    return gl, _kmt_mbg_sales_hpp(start, end), snap is None


def _values(gl, manual, codes):
    """Nilai mentah (Penjualan..Sales Net) utk sekumpulan outlet; KMT/MBG dari input manual."""
    si = [c for c in codes if c not in ("KMT", "MBG")]
    gl_sum = {acc: sum(gl.get(o, {}).get(acc, 0) or 0 for o in si) for acc in _GL_MARGIN_ACCOUNTS}
    m = _margin_row("x", "x", gl_sum, 0)
    vals = {k: m[k] or 0 for k in _KEYS}
    for c in codes:
        if c in ("KMT", "MBG"):
            s = manual.get(c, {}).get("sales", 0) or 0
            for k in ("sales_bruto", "sales_bruto_2", "sales_retur"):
                vals[k] += s
    return vals


def execute(filters=None):
    filters = filters or {}
    as_of = getdate(filters.get("tanggal") or today())
    ws, we = (getdate(d) for d in _monday_week_bounds(as_of))
    pws, pwe = getdate(add_days(ws, -7)), getdate(add_days(we, -7))
    gl, manual, live = _week_data(ws, we)
    gl_prev, manual_prev, live_prev = _week_data(pws, pwe)

    def row(label, codes, no=None, bold=0):
        v = _values(gl, manual, codes)
        prev = _values(gl_prev, manual_prev, codes)["sales_retur"]
        out = {"no": no, "outlet": label, "bold": bold}
        out.update({k: round(v[k]) for k in _KEYS})
        out["sales_net_prev"] = round(prev)
        out["growth"] = round((v["sales_retur"] / prev - 1) * 100, 2) if prev else None
        return out

    off = [c for c, _l, _n in _FASHION_OFFLINE]
    onl = [c for c, _l, _n in _FASHION_ONLINE]
    fmcg = [c for c, _l, _n in _FMCG]
    # Kemitraan TIDAK masuk tabel & total - ikut file: baris "Kemitraan (inc sales
    # xmk)" diisi 0, sales Kemitraan ditulis terpisah di bawah ("sales terlapor
    # kemitraan berbeda"); Total Holding & GRAND TOTAL tanpa Kemitraan.
    ho = ["MBG", "XSL"]
    data = [{"outlet": "1.FASHION & HOME.S", "bold": 1, "is_header": 1}]
    data += [row(l, [c], n) for c, l, n in _FASHION_OFFLINE]
    data.append(row("Total Outlet - Offline", off, bold=1))
    data += [row(l, [c], n) for c, l, n in _FASHION_ONLINE]
    data.append(row("Total Outlet - Online", onl, bold=1))
    data.append(row("Total Dept.F.H", off + onl, bold=1))
    data.append({"outlet": "2.FMCG", "bold": 1, "is_header": 1})
    data += [row(l, [c], n) for c, l, n in _FMCG]
    data.append(row("Total Dept.FMCG", fmcg, bold=1))
    data.append({"outlet": "4.HO", "bold": 1, "is_header": 1})
    data += [row("MBG", ["MBG"]), row("Kemitraan (inc sales xmk)", []), row("Minisoccer", ["XSL"])]
    data.append(row("Total Dept.Holding", ho, bold=1))
    data.append(row("GRAND TOTAL", off + onl + fmcg + ho, bold=1))
    data.append({})
    data.append(row("Kemitraan / kmt (sales terlapor berbeda, tdk masuk total)", ["KMT"]))

    info = (f"Minggu: {formatdate(ws, 'dd')}-{formatdate(we, 'dd MMMM yyyy')} (Senin-Minggu)  |  "
            f"minggu lalu: {formatdate(pws, 'dd')}-{formatdate(pwe, 'dd MMMM yyyy')}")
    lives = [t for t, f in (("minggu ini", live), ("minggu lalu", live_prev)) if f]
    if lives:
        info += f"  |  (live: {', '.join(lives)})"
    data.insert(0, {"outlet": info, "bold": 1, "is_info": 1})
    return get_columns(), data


def get_columns():
    def col(fieldname, label, fieldtype="Int", width=130):
        return {"fieldname": fieldname, "label": label, "fieldtype": fieldtype, "width": width}
    return [
        col("no", _("No"), "Data", 45),
        col("outlet", _("Outlet / Department"), "Data", 220),
        col("sales_bruto", _("Penjualan"), width=140),
        col("member", _("MEMBER-X")),
        col("potongan_penjualan", _("Potongan Penjualan")),
        col("promo", _("Promo - X")),
        col("rafaksi_discount", _("RAFAKSI DISCOUNT - X")),
        col("sales_bruto_2", _("SALES BRUTO 2"), width=140),
        col("retur_penjualan", _("RETUR PENJUALAN")),
        col("sales_retur", _("SALES - RETUR (Net)"), width=140),
        col("sales_net_prev", _("Sales Net Minggu Lalu"), width=140),
        col("growth", _("Growth vs Minggu Lalu"), "Percent", 110),
    ]
