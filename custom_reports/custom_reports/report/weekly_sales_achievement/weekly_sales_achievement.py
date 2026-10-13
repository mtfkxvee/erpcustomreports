# Copyright (c) 2026, X-SHA and contributors
# For license information, please see license.txt
#
# Laporan "Weekly Sales Achievement" - tampilan ERP dari file "SALES REPORT HO"
# sheet "Data weekly" (susunan baris & kolom mengikuti file). Rumus = API
# sales_api.get_weekly_sales_achievement & get_weekly_visitor_achievement
# (divalidasi thd SALES REPORT HO SEPT 2026: TC & Sales W1-W2, Juli & Agustus
# cocok persis). Minggu = blok tgl 1-7 / 8-14 / 15-21 / 22-akhir bulan.
#  - Tampilan "Mingguan" = bagian kiri sheet (TC/Sales/AC/Visitor per minggu,
#    growth vs minggu sebelumnya, MTD).
#  - Tampilan "Pembanding" = bagian kanan sheet (Sales per minggu vs tahun lalu
#    & 2 bulan sebelumnya).
#  - Sales Invoice dibaca dari snapshot penjualan harian (sales_snapshot.py,
#    sama dgn Daily Sales vs Target) kalau minggu itu lengkap snapshot-nya,
#    kalau tidak dihitung live & diberi label "(live)". Visitor (POS Closing
#    Shift), data histori & KMT/MBG tetap dibaca langsung.

import frappe
from frappe import _
from frappe.utils import getdate, today

from custom_reports.sales_api import (
    _BULAN_ID,
    _FASHION_OFFLINE,
    _FASHION_ONLINE,
    _MBG_OUTLET,
    _MINI_SOCCER_OUTLET,
    _WEEKLY_OUTLETS,
    _month_tc_sales,
    _month_visitor,
    _r,
    _sales_by_outlet,
    _week_bounds,
)
from custom_reports.sales_snapshot import load_sales

_TAMPILAN = ["Mingguan", "Pembanding"]
_SHORT = {"Juli": "Jul", "Agustus": "Ags"}

_LAYOUT = [
    ("FASHION & H S", [
        ("XSC", "Cikiray", 1), ("PSR", "Pasar", 2), ("XPY", "Panyingkiran", 3), ("XJB", "Furniture", 4),
        ("XCW", "Ciawi", 5), ("XSP", "SP Fashion", 6), ("HCW", "X-sha Rumah Kedua", 7),
        ("=Total Outlet - Offline", _FASHION_OFFLINE, None),
        ("XSC-OL", "online cikiray", None), ("OCW", "online ciawi", None), ("XSP-OL", "online SP Fashion", None),
        ("=Total Outlet - Online", _FASHION_ONLINE, None),
        ("=FASHION & H S", _FASHION_OFFLINE + _FASHION_ONLINE, None),
    ]),
    ("FMCG", [
        ("XSM", "Supermart", 1), ("XMJ", "X-Shamart Mangunreja", 2), ("XWP", "X-Shamart Warung peuteuy", 3),
        ("XPH", "X-Shamart Puspahiang", 4), ("XTJ", "X-Shamart Tanjung jaya", 5), ("XCR", "X-Shamart Cisaruni", 6),
        ("TASMU", "Tasmu Mart", 7), ("MNR", "Menara X-Shamart", 8), ("UIN", "UIN Grow", 9), ("XSMGROW", "XSM Grow", 10),
        ("=FMCG", ["XSM", "XMJ", "XWP", "XPH", "XTJ", "XCR", "TASMU", "MNR", "UIN", "XSMGROW"], None),
    ]),
    ("HO", [
        (_MINI_SOCCER_OUTLET, "Mini Soccer", None), ("KMT", "Marketing sales (incl mitra)", None), (_MBG_OUTLET, "MBG", None),
        ("=HOLDING", _WEEKLY_OUTLETS, None),
    ]),
]


def _pct(new, old):
    return round((new / old - 1) * 100, 2) if (old and new is not None) else None


def _ac(sales, tc):
    return sales / tc if tc else None


def execute(filters=None):
    filters = filters or {}
    now = getdate(today())
    month = _BULAN_ID.index(filters.get("bulan")) + 1 if filters.get("bulan") in _BULAN_ID else now.month
    year = int(filters.get("tahun") or now.year)
    tampilan = filters.get("tampilan") or "Mingguan"
    if tampilan not in _TAMPILAN:
        frappe.throw(_("Tampilan tidak dikenal: {0}").format(tampilan))

    m1, y1 = (month - 1, year) if month > 1 else (12, year - 1)
    m2, y2 = (m1 - 1, y1) if m1 > 1 else (12, y1 - 1)

    live_weeks = set()

    def sales_fn_for(label):
        def fn(start, end):
            snap = load_sales(start, end)
            if snap is None:
                if getdate(start) <= now:  # minggu yg blm terjadi tdk dianggap "live"
                    live_weeks.add(label)
                return _sales_by_outlet(start, end)
            return snap
        return fn

    cur = _month_tc_sales(year, month, _WEEKLY_OUTLETS, sales_fn_for(f"{_BULAN_ID[month - 1]} {year}"))
    visitor = _month_visitor(year, month, _WEEKLY_OUTLETS)
    if tampilan == "Pembanding":
        lm1 = _month_tc_sales(y1, m1, _WEEKLY_OUTLETS, sales_fn_for(f"{_BULAN_ID[m1 - 1]} {y1}"))
        lm2 = _month_tc_sales(y2, m2, _WEEKLY_OUTLETS, sales_fn_for(f"{_BULAN_ID[m2 - 1]} {y2}"))
        ly = _month_tc_sales(year - 1, month, _WEEKLY_OUTLETS, sales_fn_for(f"{_BULAN_ID[month - 1]} {year - 1}"))

    def week_vals(src, i, outlets):
        tc = sum(src[i].get(o, {}).get("trx", 0) or 0 for o in outlets)
        sales = sum(src[i].get(o, {}).get("sales", 0) or 0 for o in outlets)
        return tc, sales

    def mingguan_row(outlets):
        row, prev = {}, None
        mtd_tc = mtd_sales = mtd_v = 0
        for i in range(4):
            tc, sales = week_vals(cur, i, outlets)
            v = sum(visitor[i].get(o, 0) or 0 for o in outlets)
            ac = _ac(sales, tc)
            w = i + 1
            row.update({f"w{w}_tc": _r(tc), f"w{w}_sales": _r(sales), f"w{w}_ac": _r(ac) if ac is not None else None, f"w{w}_visitor": _r(v)})
            if prev:
                row.update({
                    f"g{w}_tc": _pct(tc, prev[0]), f"g{w}_sales": _pct(sales, prev[1]),
                    f"g{w}_ac": _pct(ac, prev[2]), f"g{w}_visitor": _pct(v, prev[3]),
                })
            prev = (tc, sales, ac, v)
            mtd_tc += tc; mtd_sales += sales; mtd_v += v
        mtd_ac = _ac(mtd_sales, mtd_tc)
        row.update({"mtd_tc": _r(mtd_tc), "mtd_sales": _r(mtd_sales), "mtd_ac": _r(mtd_ac) if mtd_ac is not None else None, "mtd_visitor": _r(mtd_v)})
        return row

    def pembanding_row(outlets):
        row = {}
        for i in range(4):
            w = i + 1
            _tc, sales = week_vals(cur, i, outlets)
            _x, s_ly = week_vals(ly, i, outlets)
            _y, s_m1 = week_vals(lm1, i, outlets)
            _z, s_m2 = week_vals(lm2, i, outlets)
            row.update({
                f"p{w}_cur": _r(sales), f"p{w}_ly": _r(s_ly), f"p{w}_ly_growth": _pct(sales, s_ly),
                f"p{w}_m2": _r(s_m2), f"p{w}_m1": _r(s_m1), f"p{w}_vs_m2": _pct(sales, s_m2), f"p{w}_vs_m1": _pct(sales, s_m1),
            })
        return row

    build = mingguan_row if tampilan == "Mingguan" else pembanding_row
    data = []
    for section, items in _LAYOUT:
        data.append({"outlet": section, "bold": 1, "is_header": 1})
        for code, label_or_outlets, no in items:
            if code.startswith("="):
                row = build(label_or_outlets); row.update({"outlet": code[1:], "bold": 1})
            else:
                row = build([code]); row.update({"outlet": label_or_outlets, "no": no})
            data.append(row)

    bounds = _week_bounds(year, month)
    info = f"{_BULAN_ID[month - 1]} {year}  |  " + "  ".join(f"W{i + 1}: tgl {s}-{e}" for i, (s, e) in enumerate(bounds))
    if live_weeks:
        info += f"  |  (live: {', '.join(sorted(live_weeks))})"
    data.insert(0, {"outlet": info, "bold": 1, "is_info": 1})

    if tampilan == "Mingguan":
        return mingguan_columns(), data
    return pembanding_columns(month, year, m1, m2), data


def _col(fieldname, label, fieldtype="Int", width=100):
    return {"fieldname": fieldname, "label": label, "fieldtype": fieldtype, "width": width}


def mingguan_columns():
    cols = [_col("no", _("No"), "Data", 45), _col("outlet", _("Outlet"), "Data", 220)]
    for w in range(1, 5):
        cols += [_col(f"w{w}_tc", f"W{w} TC"), _col(f"w{w}_sales", f"W{w} Sales", width=130),
                 _col(f"w{w}_ac", f"W{w} AC"), _col(f"w{w}_visitor", f"W{w} Visitor")]
        if w > 1:
            cols += [_col(f"g{w}_tc", f"Growth W{w} TC", "Percent"), _col(f"g{w}_sales", f"Growth W{w} Sales", "Percent"),
                     _col(f"g{w}_ac", f"Growth W{w} AC", "Percent"), _col(f"g{w}_visitor", f"Growth W{w} Visitor", "Percent")]
    cols += [_col("mtd_tc", "MTD TC"), _col("mtd_sales", "MTD Sales", width=130), _col("mtd_ac", "MTD AC"), _col("mtd_visitor", "MTD Visitor")]
    return cols


def pembanding_columns(month, year, m1, m2):
    cur_label = f"{_BULAN_ID[month - 1]} {year}"
    ly_label = f"{_BULAN_ID[month - 1]} {year - 1}"
    m1_label, m2_label = _BULAN_ID[m1 - 1], _BULAN_ID[m2 - 1]
    cols = [_col("no", _("No"), "Data", 45), _col("outlet", _("Outlet"), "Data", 220)]
    for w in range(1, 5):
        cols += [
            _col(f"p{w}_cur", f"W{w} {cur_label}", width=130), _col(f"p{w}_ly", f"W{w} {ly_label}", width=130),
            _col(f"p{w}_ly_growth", f"W{w} growth", "Percent"),
            _col(f"p{w}_m2", f"W{w} {m2_label}", width=130), _col(f"p{w}_m1", f"W{w} {m1_label}", width=130),
            _col(f"p{w}_vs_m2", f"W{w} vs {_SHORT.get(m2_label, m2_label[:3])}", "Percent"),
            _col(f"p{w}_vs_m1", f"W{w} vs {_SHORT.get(m1_label, m1_label[:3])}", "Percent"),
        ]
    return cols
