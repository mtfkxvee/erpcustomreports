# Copyright (c) 2026, X-SHA and contributors
# For license information, please see license.txt
#
# Laporan "Weekly Margin Target vs Achievement" (dulu bernama "Weekly Margin") - tampilan ERP dari file admin
# terbaru "WEEKLY MARGIN OCTOBER 2026" sheet "28-04 October" bagian "WEEKLY
# MARGIN CLEAR X-SHA GROUP" (susunan baris & kolom mengikuti file; sebelumnya
# format Agustus dgn baris "Cikiray All" dst - user 2026-10-14: ikut file
# terbaru). Rumus = API sales_api.get_weekly_margin (_margin_row), divalidasi
# thd file tsb minggu 28 Sep-4 Okt 2026. Minggu = Senin-Minggu.
#  - Exclude promo: Deal Margin = Sales-Retur - HPP, Sales Achv = Sales-Retur,
#    Margin = Deal Margin / Sales Achv.
#  - Include promo: Sales Achv = Sales-Retur + PROMO-X + RAFAKSI (file: W = R +
#    T + U), Deal Margin = Sales Achv - HPP, Margin = V / W, ACHV = Margin /
#    Target.
#  - Target margin = sales_api._MARGIN_TARGET_PCT (dokumen Semester II, Ciawi
#    25% spt file); Total Outlet Offline 24%, Online 22%, Total dept = target
#    dept, TOTAL = target HO bulanan.
#  - Jurnal potongan & HPP outlet dibaca dari snapshot harian (sales_snapshot)
#    kalau minggu itu lengkap, kalau tidak live + label "(live)".
#  - Kemitraan & MBG: sales + HPP dari input manual "Kemitraan MBG Sales History"
#    (field HPP); kalau HPP blm diinput, margin dikosongkan & tdk ikut TOTAL.
#    Di bawah TOTAL: rincian Kemitraan per mitra (RSI/FDM/ANM/UMTAS) spt file.

import frappe
from frappe import _
from frappe.utils import formatdate, getdate, today

from custom_reports.sales_api import (
    _GL_MARGIN_ACCOUNTS,
    _MARGIN_DEPT_TARGET_PCT,
    _MARGIN_TARGET_PCT,
    _OUTLET_COST_CENTER,
    _gl_deductions_by_outlet,
    _hpp_by_outlet,
    _margin_row,
    _monday_week_bounds,
)
from custom_reports.sales_snapshot import load_margin

# Target margin HO per bulan, Semester II 2026 (RESUME TARGET MARGIN, kolom E)
_HO_TARGET_BY_MONTH = {7: 0.20858447488584475, 8: 0.20804878048780487, 9: 0.20626506024096386,
                       10: 0.2065871121718377, 11: 0.20738041002277904, 12: 0.20793388429752066}


def _ho_target(year, month):
    """Target margin HO bulan itu, dibulatkan 4 desimal (= 2 desimal %) spt yg
    diketik admin di file: WEEKLY MARGIN OCTOBER 0,2066 & SALES & MARGIN ACHV
    AGUSTUS 0,208. None kalau di luar Semester II 2026."""
    t = _HO_TARGET_BY_MONTH.get(month) if year == 2026 else None
    return round(t, 4) if t else None


# RESUME TARGET MARGIN: Total Outlet - Offline 24%, Total Outlet - Online 22%
_OFFLINE_TARGET, _ONLINE_TARGET = 0.24, 0.22

# (kode, label, no) - urutan spt file
_FASHION_OFFLINE = [("XSC", "Cikiray", 1), ("PSR", "Pasar", 2), ("XPY", "Panyingkiran", 3), ("XJB", "Furniture", 4),
                    ("XCW", "Ciawi", 5), ("XSP", "SP Fashion", 6), ("HCW", "X-sha Rumah Kedua", 7)]
_FASHION_ONLINE = [("XSC-OL", "Online Cikiray", None), ("OCW", "Online Ciawi", None), ("XSP-OL", "Online SP Fashion", None)]
_FMCG = [("XSM", "Supermart", 1), ("XMJ", "X-Shamart Mangunreja", 2), ("XWP", "X-Shamart Warung Peuteuy", 3),
         ("XPH", "X-Shamart Puspahiang", 4), ("XTJ", "X-Shamart Tanjung jaya", 5), ("XCR", "X-Shamart Cisaruni", 6),
         ("TASMU", "Tasmu Mart", 7), ("MNR", "Menara X-Shamart", 8), ("UIN", "UIN Grow", 9), ("XSMGROW", "XSM Grow", 10)]
_MITRA = ["RSI", "FDM", "ANM", "UMTAS"]


def _codes(items):
    return [c for c, _l, _n in items]


def _kmt_mbg_sales_hpp(start, end):
    """{KMT|MBG: {"sales", "hpp", "hpp_filled"}} dari Kemitraan MBG Sales History
    (sub_kode SKM selalu di-exclude - rollup/duplikat, lihat sales_api)."""
    rows = frappe.db.sql("""
        SELECT kategori, SUM(nominal) AS sales, SUM(COALESCE(hpp, 0)) AS hpp,
               SUM(CASE WHEN COALESCE(hpp, 0) <> 0 THEN 1 ELSE 0 END) AS n_hpp
        FROM `tabKemitraan MBG Sales History`
        WHERE tanggal BETWEEN %s AND %s AND sub_kode != 'SKM'
        GROUP BY kategori
    """, (start, end), as_dict=True)
    mapping = {"Kemitraan": "KMT", "MBG": "MBG"}
    return {mapping[r.kategori]: {"sales": r.sales or 0, "hpp": r.hpp or 0, "hpp_filled": bool(r.n_hpp)}
            for r in rows if r.kategori in mapping}


def _kmt_by_mitra(start, end):
    """{sub_kode: {"sales", "hpp", "hpp_filled"}} Kemitraan per mitra."""
    rows = frappe.db.sql("""
        SELECT sub_kode, SUM(nominal) AS sales, SUM(COALESCE(hpp, 0)) AS hpp,
               SUM(CASE WHEN COALESCE(hpp, 0) <> 0 THEN 1 ELSE 0 END) AS n_hpp
        FROM `tabKemitraan MBG Sales History`
        WHERE tanggal BETWEEN %s AND %s AND kategori = 'Kemitraan' AND sub_kode != 'SKM'
        GROUP BY sub_kode
    """, (start, end), as_dict=True)
    return {r.sub_kode: {"sales": r.sales or 0, "hpp": r.hpp or 0, "hpp_filled": bool(r.n_hpp)} for r in rows}


def execute(filters=None):
    filters = filters or {}
    as_of = getdate(filters.get("tanggal") or today())
    week_start, week_end = _monday_week_bounds(as_of)
    week_start, week_end = getdate(week_start), getdate(week_end)

    outlets = list(_OUTLET_COST_CENTER)
    snap = load_margin(week_start, week_end)
    is_live = snap is None
    if is_live:
        gl_data = _gl_deductions_by_outlet(week_start, week_end, outlets)
        hpp_data = _hpp_by_outlet(week_start, week_end, outlets)
    else:
        gl_data, hpp_data = snap
    manual = _kmt_mbg_sales_hpp(week_start, week_end)

    def gl_sum(codes):
        return {acc: sum(gl_data.get(o, {}).get(acc, 0) or 0 for o in codes) for acc in _GL_MARGIN_ACCOUNTS}

    def build(label, codes, target, no=None, bold=0):
        m = _margin_row(label, label, gl_sum(codes), sum(hpp_data.get(o, 0) or 0 for o in codes), target_pct=target)
        return _row(m, label, target, no, bold)

    def manual_row(label, d, target):
        d = d or {"sales": 0, "hpp": 0, "hpp_filled": False}
        row = {"no": None, "outlet": label, "sales_retur": d["sales"], "sales_achv": d["sales"], "promo": 0, "rafaksi": 0,
               "target": target * 100 if target else None, "_sales": d["sales"], "_margin": None}
        if d["hpp_filled"]:
            margin = d["sales"] - d["hpp"]
            pct = margin / d["sales"] if d["sales"] else None
            row.update({"deal_margin_clear": margin, "deal_margin_plus": margin, "_margin": margin,
                        "margin_pct": pct * 100 if pct is not None else None,
                        "margin_pct_incl": pct * 100 if pct is not None else None,
                        "achv": (pct / target * 100) if (pct is not None and target) else None})
        return row

    off, onl, fmcg = _codes(_FASHION_OFFLINE), _codes(_FASHION_ONLINE), _codes(_FMCG)
    data = [{"outlet": "FASHION & H.S", "bold": 1, "is_header": 1}]
    data += [build(label, [c], _MARGIN_TARGET_PCT.get(c), no) for c, label, no in _FASHION_OFFLINE]
    data.append(build("Total Outlet - Offline", off, _OFFLINE_TARGET, bold=1))
    data += [build(label, [c], _MARGIN_TARGET_PCT.get(c), no) for c, label, no in _FASHION_ONLINE]
    data.append(build("Total Outlet - Online", onl, _ONLINE_TARGET, bold=1))
    data.append(build("Total", off + onl, _MARGIN_DEPT_TARGET_PCT.get("FASHION"), bold=1))
    data.append({"outlet": "FMCG", "bold": 1, "is_header": 1})
    data += [build(label, [c], _MARGIN_TARGET_PCT.get(c), no) for c, label, no in _FMCG]
    data.append(build("Total", fmcg, _MARGIN_DEPT_TARGET_PCT.get("FMCG"), bold=1))

    kmt = manual_row("X-Sha Kemitraan", manual.get("KMT"), _MARGIN_TARGET_PCT.get("KMT"))
    xsl = build("Mini Soccer", ["XSL"], _MARGIN_TARGET_PCT.get("XSL"))
    mbg = manual_row("MBG (Dapur)", manual.get("MBG"), _MARGIN_TARGET_PCT.get("MBG"))
    data += [kmt, xsl, mbg]

    # TOTAL = Fashion + FMCG + Mini Soccer + (KMT/MBG yg HPP-nya sudah diinput)
    si_codes = off + onl + fmcg + ["XSL"]
    m = _margin_row("TOTAL", "TOTAL", gl_sum(si_codes), sum(hpp_data.get(o, 0) or 0 for o in si_codes))
    clear, sales_r = m["deal_margin_clear"], m["sales_retur"]
    plus, achv_sales = m["deal_margin_plus"], m["sales_achv"]
    excluded = []
    for r in (kmt, mbg):
        if r["_margin"] is None:
            excluded.append(r["outlet"])
            continue
        clear += r["_margin"]; plus += r["_margin"]; sales_r += r["_sales"]; achv_sales += r["_sales"]
    ho_target = _ho_target(as_of.year, as_of.month)
    pct_incl = plus / achv_sales if achv_sales else None
    data.append({
        "outlet": "TOTAL", "bold": 1, "deal_margin_clear": clear, "sales_retur": sales_r,
        "margin_pct": clear / sales_r * 100 if sales_r else None, "promo": m["promo"], "rafaksi": m["rafaksi_discount"],
        "deal_margin_plus": plus, "sales_achv": achv_sales,
        "margin_pct_incl": pct_incl * 100 if pct_incl is not None else None,
        "target": ho_target * 100 if ho_target else None,
        "achv": pct_incl / ho_target * 100 if (pct_incl is not None and ho_target) else None,
    })

    # rincian Kemitraan per mitra (file: tabel LABA / SALES / % di bawah TOTAL)
    mitra = _kmt_by_mitra(week_start, week_end)
    data.append({})
    data.append({"outlet": "Kemitraan per mitra", "bold": 1, "is_header": 1})
    def mitra_row(label, d, bold=0):
        # file: per mitra cuma kolom LABA / SALES / %
        r = manual_row(label, d, None)
        return {"outlet": label, "bold": bold, "deal_margin_clear": r.get("deal_margin_clear"),
                "sales_retur": r["sales_retur"], "margin_pct": r.get("margin_pct")}
    data += [mitra_row(code, mitra.get(code)) for code in _MITRA]
    data.append(mitra_row("Total Kemitraan", manual.get("KMT"), bold=1))

    for r in data:
        for k in [k for k in r if k.startswith("_")]:
            r.pop(k)
        for k in ("deal_margin_clear", "sales_retur", "promo", "rafaksi", "deal_margin_plus", "sales_achv"):
            if r.get(k) is not None:
                r[k] = round(r[k])
        for k in ("margin_pct", "margin_pct_incl", "target", "achv"):
            if r.get(k) is not None:
                r[k] = round(r[k], 2)

    info = f"Periode: {formatdate(week_start, 'dd')}-{formatdate(week_end, 'dd MMMM yyyy')} (Senin-Minggu)"
    if is_live:
        info += "  |  (live)"
    if excluded:
        info += f"  |  {', '.join(excluded)}: HPP blm diinput -> margin kosong & tdk ikut TOTAL"
    data.insert(0, {"outlet": info, "bold": 1, "is_info": 1})
    return get_columns(), data


def _row(m, label, target, no, bold):
    return {
        "no": no, "outlet": label, "bold": bold,
        "deal_margin_clear": m["deal_margin_clear"], "sales_retur": m["sales_retur"], "margin_pct": m["margin_pct"],
        "promo": m["promo"], "rafaksi": m["rafaksi_discount"],
        "deal_margin_plus": m["deal_margin_plus"], "sales_achv": m["sales_achv"],
        "margin_pct_incl": m["margin_pct_incl"], "target": target * 100 if target else None, "achv": m["achv_pct"],
    }


def get_columns():
    def col(fieldname, label, fieldtype="Int", width=130):
        return {"fieldname": fieldname, "label": label, "fieldtype": fieldtype, "width": width}
    return [
        col("no", _("No"), "Data", 45),
        col("outlet", _("Outlet"), "Data", 220),
        col("deal_margin_clear", _("Exclude Promo: Deal Margin")),
        col("sales_retur", _("Exclude Promo: Sales Achv"), width=140),
        col("margin_pct", _("Exclude Promo: Margin"), "Percent", 110),
        col("promo", _("PROMO-X")),
        col("rafaksi", _("RAFAKSI DISCOUNT - X")),
        col("deal_margin_plus", _("Include Promo: Deal Margin")),
        col("sales_achv", _("Include Promo: Sales Achv"), width=140),
        col("margin_pct_incl", _("Include Promo: Margin"), "Percent", 110),
        col("target", _("Target"), "Percent", 90),
        col("achv", _("ACHV"), "Percent", 90),
    ]
