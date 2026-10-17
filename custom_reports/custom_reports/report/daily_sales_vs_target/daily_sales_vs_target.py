# Copyright (c) 2026, X-SHA and contributors
# For license information, please see license.txt
#
# Laporan "Daily Sales vs Target" - tampilan ERP dari file "SALES REPORT HO"
# sheet ALL / DEPT. F&H.S / DEPT. FMCG (susunan baris & kolom mengikuti file).
# Rumus = API sales_api.get_sales_vs_target_detail (divalidasi thd SALES REPORT
# HO OCT 2026 per 4/10/26: target, daily, akumulasi, MTD bulan lalu, MTD &
# monthly tahun lalu cocok persis). Bedanya dgn API (API sendiri TIDAK diubah):
#  - Daily, akumulasi & MTD bulan lalu dibaca dari snapshot harian
#    (sales_snapshot.py) kalau lengkap, supaya angka tgl lewat tdk berubah;
#    kalau blm lengkap dihitung live & diberi label "(live)".
#  - Balance To Achv 90%/100% bertanda spt file (akumulasi - target, negatif).
#  - VS Standard Achv dihitung dari nilai blm dibulatkan (spt file).
#  - F&H.S: outlet online cukup 1 baris "Total Outlet - Online" (spt file).
#  - Baris bantu FMCG ("MBG Supermart",
#    "Total Supermart", dst) ikut ditampilkan spt file, dgn angka yg benar.
# Sel file yg rumus Excel-nya salah (balance Pasar & Panyingkiran, MTD bulan
# lalu XSM Grow, % 2026 vs 2025 TOTAL Exclude UIN & HCW) TIDAK ditiru.

import calendar

import frappe
from frappe import _
from frappe.utils import add_days, getdate, today

from custom_reports.sales_api import (
    _BULAN_ID,
    _FASHION_OFFLINE,
    _FASHION_ONLINE,
    _FMCG_ALL,
    _MINI_SOCCER_OUTLET,
    _kmt_only,
    _r,
    _sales_by_kmt_mbg,
    _sales_by_outlet,
    _sales_by_outlet_history,
    _target_by_outlet,
)
from custom_reports.sales_snapshot import load_sales

_DEPTS = ["ALL", "DEPT. F&H.S", "DEPT. FMCG"]

# label per sheet file
_FASHION_LABELS = {
    "XSC": "Cikiray", "PSR": "Pasar", "XPY": "Panyingkiran", "XJB": "Furniture", "XCW": "Ciawi",
    "XSP": "Sp Fashion", "HCW": "X-sha rumah kedua",
    "XSC-OL": "Online Cikiray", "OCW": "Online Ciawi", "XSP-OL": "Online Sp Fashion",
}
_FASHION_ORDER = ["XSC", "PSR", "XPY", "XJB", "XCW", "XSP", "HCW"]
# (kode, label, nama pendek utk baris bantu "MBG x"/"Total x" - None = tanpa baris bantu)
_FMCG_LAYOUT = [
    ("XSM", "Supermart", "Supermart"),
    ("XMJ", "X-Shamart Mangunreja", "Mangunreja"),
    ("XWP", "X-Shamart Wr Peuteuy", "Wr Peuteuy"),
    ("XPH", "X-Shamart Puspahiang", "Puspahiang"),
    ("XTJ", "X-Shamart Tanjung jaya", "Tanjung jaya"),
    ("XCR", "X-Shamart Cisaruni", "Cisaruni"),
    ("TASMU", "Tasmu Mart", "Tasmu"),
    ("MNR", "Menara X-Shamart", "Menara"),
    ("UIN", "UIN Grow", None),
    ("XSMGROW", "XSM Grow", None),
    ("KMT", "Kemitraan", None),
    ("MBG", "MBG", None),
]
_EN_MONTH = list(calendar.month_name)  # judul kolom file pakai nama bulan Inggris


def _pct(new, old):
    return round((new / old - 1) * 100, 2) if old else None


def execute(filters=None):
    filters = filters or {}
    as_of = getdate(filters.get("tanggal") or today())
    dept = filters.get("departemen") or "ALL"
    if dept not in _DEPTS:
        frappe.throw(_("Departemen tidak dikenal: {0}").format(dept))

    # --- periode (sama persis dgn get_sales_vs_target_detail) ---
    month_start = as_of.replace(day=1)
    days_in_month = calendar.monthrange(as_of.year, as_of.month)[1]
    standard = as_of.day / days_in_month  # pecahan, spt file
    remaining_days = days_in_month - as_of.day
    last_month_end = getdate(add_days(month_start, -1))
    last_month_start = last_month_end.replace(day=1)
    lm_day = min(as_of.day, calendar.monthrange(last_month_end.year, last_month_end.month)[1])
    last_month_mtd_end = last_month_start.replace(day=lm_day)
    ly = as_of.year - 1
    ly_days = calendar.monthrange(ly, as_of.month)[1]
    ly_start = getdate(f"{ly}-{as_of.month:02d}-01")
    ly_mtd_end = getdate(f"{ly}-{as_of.month:02d}-{min(as_of.day, ly_days):02d}")
    ly_month_end = getdate(f"{ly}-{as_of.month:02d}-{ly_days:02d}")

    # --- sumber data: snapshot kalau lengkap, kalau tidak live ---
    live_parts = []

    def sales_src(start, end, part):
        snap = load_sales(start, end)
        if snap is None:
            live_parts.append(part)
            return dict(_sales_by_outlet(start, end))
        return snap

    daily = sales_src(as_of, as_of, "daily")
    accumulated = sales_src(month_start, as_of, "akumulasi")
    mtd_last_month = sales_src(last_month_start, last_month_mtd_end, "MTD bulan lalu")
    mtd_last_year = dict(_sales_by_outlet_history(ly_start, ly_mtd_end))
    monthly_last_year = dict(_sales_by_outlet_history(ly_start, ly_month_end))
    # KMT & MBG: periode "sekarang-ish" include keduanya, "tahun lalu" cuma KMT
    # (sama dgn API - lihat docstring sales_api._kmt_only).
    daily.update(_sales_by_kmt_mbg(as_of, as_of))
    accumulated.update(_sales_by_kmt_mbg(month_start, as_of))
    mtd_last_month.update(_sales_by_kmt_mbg(last_month_start, last_month_mtd_end))
    mtd_last_year.update(_kmt_only(ly_start, ly_mtd_end))
    monthly_last_year.update(_kmt_only(ly_start, ly_month_end))
    targets = _target_by_outlet(_BULAN_ID[as_of.month - 1])

    def get(src, outlet):
        v = src.get(outlet, {})
        return v.get("trx", 0) or 0, v.get("sales", 0) or 0

    def calc(label, outlets, subtotal=False, balance=True, no=None, bold=0):
        d_tc = sum(get(daily, o)[0] for o in outlets); d_sales = sum(get(daily, o)[1] for o in outlets)
        a_tc = sum(get(accumulated, o)[0] for o in outlets); a_sales = sum(get(accumulated, o)[1] for o in outlets)
        # subtotal: XSM Grow di-exclude dari "Last month" (konvensi laporan admin, sama dgn API)
        lm_outlets = [o for o in outlets if o != "XSMGROW"] if subtotal else outlets
        lm_tc = sum(get(mtd_last_month, o)[0] for o in lm_outlets); lm_sales = sum(get(mtd_last_month, o)[1] for o in lm_outlets)
        ly_tc = sum(get(mtd_last_year, o)[0] for o in outlets); ly_sales = sum(get(mtd_last_year, o)[1] for o in outlets)
        myly_sales = sum(get(monthly_last_year, o)[1] for o in outlets)
        target = round(sum(targets.get(o, 0) for o in outlets), 2)
        achv = (a_sales / target) if target else None
        row = {
            "no": no, "outlet": label, "bold": bold, "target": target,
            "daily_tc": _r(d_tc), "daily_sales": _r(d_sales), "acc_tc": _r(a_tc), "acc_sales": _r(a_sales),
            "achv": round(achv * 100, 2) if achv is not None else None,
            "vs_standard": round((achv - standard) * 100, 2) if achv is not None else None,
            "lm_tc": _r(lm_tc), "lm_sales": _r(lm_sales),
            "vs_lm_tc": _pct(a_tc, lm_tc), "vs_lm_sales": _pct(a_sales, lm_sales),
            "ly_tc": _r(ly_tc), "ly_sales": _r(ly_sales),
            "vs_ly_tc": _pct(a_tc, ly_tc), "vs_ly_sales": _pct(a_sales, ly_sales),
            "myly_sales": _r(myly_sales), "vs_myly": _pct(a_sales, myly_sales),
        }
        if balance:
            for pct, key in ((0.9, "90"), (1.0, "100")):
                bal = a_sales - target * pct  # spt file: akumulasi - target (negatif = masih kurang)
                row[f"target_{key}"] = _r(target * pct)
                row[f"balance_{key}"] = _r(bal)
                row[f"avg_{key}"] = _r(bal / remaining_days) if remaining_days else None
        return row

    fashion_all = _FASHION_OFFLINE + _FASHION_ONLINE
    data = []
    if dept == "ALL":
        data.append({"outlet": "1.Fashion and Home supplies :", "bold": 1})
        data.append(calc("F&H.S exclude HCW", [o for o in fashion_all if o != "HCW"], subtotal=True, balance=False))
        data.append(calc("Total", fashion_all, subtotal=True, bold=1))
        data.append({"outlet": "2.FMCG :", "bold": 1})
        data.append(calc("Fmcg exclude MBG", [o for o in _FMCG_ALL if o != "MBG"], subtotal=True, balance=False))
        data.append(calc("Fmcg exclude UIN", [o for o in _FMCG_ALL if o != "UIN"], subtotal=True, balance=False))
        data.append(calc("Total", _FMCG_ALL, subtotal=True, bold=1))
        data.append(calc("3.Mini Soccer", [_MINI_SOCCER_OUTLET], bold=1))
        data.append({})
        data.append(calc("TOTAL Exclude MBG", fashion_all + [o for o in _FMCG_ALL if o != "MBG"] + [_MINI_SOCCER_OUTLET],
                         subtotal=True, balance=False, bold=1))
        data.append(calc("TOTAL Exclude UIN & HCW", [o for o in fashion_all if o != "HCW"] + [o for o in _FMCG_ALL if o != "UIN"]
                         + [_MINI_SOCCER_OUTLET], subtotal=True, balance=False, bold=1))
        data.append(calc("GRAND TOTAL", fashion_all + _FMCG_ALL + [_MINI_SOCCER_OUTLET], subtotal=True, bold=1))
    elif dept == "DEPT. F&H.S":
        # Outlet online TIDAK dirinci per outlet, langsung 1 baris "Total Outlet -
        # Online" - spt file SALES REPORT HO OCT 2026 & API (user 2026-10-16).
        data.append({"outlet": "Outlet Offline", "bold": 1, "is_header": 1})
        for i, o in enumerate(_FASHION_ORDER, 1):
            data.append(calc(_FASHION_LABELS[o], [o], no=i))
        data.append(calc("Total Outlet - Offline", _FASHION_OFFLINE, subtotal=True, bold=1))
        data.append({"outlet": "Outlet Online", "bold": 1, "is_header": 1})
        data.append(calc("Total Outlet - Online", _FASHION_ONLINE, subtotal=True, bold=1))
        data.append(calc("TOTAL DEPT. F&H.S EXC HCW", [o for o in fashion_all if o != "HCW"], subtotal=True, bold=1))
        data.append(calc("TOTAL DEPT. F&H.S ALL", fashion_all, subtotal=True, bold=1))
    else:
        for i, (o, label, short) in enumerate(_FMCG_LAYOUT, 1):
            data.append(calc(label, [o], no=i))
            if short:
                # baris bantu spt file: MBG per toko (selalu 0 - MBG dicatat sbg outlet sendiri)
                data.append(calc(f"MBG {short}", [], balance=False))
                data.append(calc(f"Total {short}", [o], balance=False))
        data.append(calc("FMCG Exclude MBG", [o for o in _FMCG_ALL if o != "MBG"], subtotal=True, bold=1))
        data.append(calc("TOTAL DEPT.FMCG ALL", _FMCG_ALL, subtotal=True, bold=1))
        data.append(calc("TOTAL DEPT.FMCG EXC UIN", [o for o in _FMCG_ALL if o != "UIN"], subtotal=True, balance=False, bold=1))
        data.append(calc("TOTAL MBG", ["MBG"], subtotal=True, balance=False, bold=1))

    info = (f"Month : {as_of.day} {_EN_MONTH[as_of.month]} {as_of.year}  |  Standard Achieve : {standard * 100:.2f}%"
            f"  |  Balance of the day to go : {remaining_days}")
    if live_parts:
        info += f"  |  (live: {', '.join(live_parts)})"
    data.insert(0, {"outlet": info, "bold": 1, "is_info": 1})

    lm_label = _EN_MONTH[last_month_end.month]
    ly_label = f"{_EN_MONTH[as_of.month]} {ly}"
    return get_columns(lm_label, ly_label), data


def get_columns(lm_label, ly_label):
    def col(fieldname, label, fieldtype="Int", width=120):
        return {"fieldname": fieldname, "label": label, "fieldtype": fieldtype, "width": width}
    return [
        col("no", _("No"), "Data", 45),
        col("outlet", _("Outlet / Department"), "Data", 230),
        col("target", _("Target"), "Int", 130),
        col("daily_tc", _("Daily TC"), "Int", 80),
        col("daily_sales", _("Daily Sales"), "Int", 120),
        col("acc_tc", _("Accumulated TC"), "Int", 100),
        col("acc_sales", _("Accumulated Sales"), "Int", 130),
        col("achv", _("Achv vs Target"), "Percent", 100),
        col("vs_standard", _("VS Standard Achv"), "Percent", 110),
        col("lm_tc", f"MTD {lm_label} TC", "Int", 100),
        col("lm_sales", f"MTD {lm_label} Sales", "Int", 130),
        col("vs_lm_tc", _("vs Last month TC"), "Percent", 100),
        col("vs_lm_sales", _("vs Last month Sales"), "Percent", 110),
        col("ly_tc", f"MTD {ly_label} TC", "Int", 100),
        col("ly_sales", f"MTD {ly_label} Sales", "Int", 130),
        col("vs_ly_tc", _("vs Last year TC"), "Percent", 100),
        col("vs_ly_sales", _("vs Last year Sales"), "Percent", 110),
        col("myly_sales", f"Monthly sales {ly_label}", "Int", 140),
        col("vs_myly", _("vs Monthly Last Year"), "Percent", 110),
        col("target_90", _("Target 90%"), "Int", 130),
        col("balance_90", _("Balance To Achv 90%"), "Int", 140),
        col("avg_90", _("Avg Daily to Achv 90%"), "Int", 140),
        col("target_100", _("Target 100%"), "Int", 130),
        col("balance_100", _("Balance To Achv 100%"), "Int", 140),
        col("avg_100", _("Avg Daily to Achv 100%"), "Int", 140),
    ]
