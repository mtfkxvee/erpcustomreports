# Copyright (c) 2026, X-SHA and contributors
# For license information, please see license.txt
#
# Laporan "Monthly Kontribusi Sales per Category" - versi bulanan dari laporan
# mingguan Kontribusi Sales per Category, tampilan dari file admin "KONTRIBUSI
# SALES CATEGORY AGUSTUS MoM YoY" (sheet F&H.S / FMCG; XSL ditambahkan spt
# laporan mingguan). Cara hitung SAMA dgn mingguan (sudah divalidasi persis ke
# file mingguan):
#   Qty & Sales = SUM(qty) & SUM(base_net_amount) Sales Invoice non-retur di
#                 warehouse group departemen, per Item.category (kalau "-" /
#                 kosong pakai item_group)
#   baris       = kategori yg laku bulan ini; bulan lalu dihitung atas baris2
#                 itu saja (file: total bulan lalu = SUM baris yg tampil)
#   Kontribusi  = sales kategori / grand total bulan itu
#   VS LAST MONTH = (kontribusi bulan ini - bulan lalu) / bulan lalu (file N =
#                 IFERROR((D-H)/H,0))
# Kolom tahun lalu di file (mis. Agustus 2025) TIDAK ada: data penjualan per
# item di ERP baru ada sejak akhir April 2026.
# Data dari snapshot kategori harian (sales_snapshot.load_category_sales) kalau
# bulan itu lengkap, kalau tidak live + label "(live)". Bulan berjalan s/d hari
# ini, bulan lalu dipotong di tgl yg sama.

import frappe
from frappe import _
from frappe.utils import getdate, today

from custom_reports.custom_reports.report.monthly_sales_achievement_vs_target_net_retur_dan_potongan.monthly_sales_achievement_vs_target_net_retur_dan_potongan import _period
from custom_reports.sales_api import _BULAN_ID, _KATEGORI_DEPT_WAREHOUSE, _category_sales_by_warehouse
from custom_reports.sales_snapshot import load_category_sales

_DEPARTEMEN = {"F&H.S": "FASHION", "FMCG": "FMCG", "XSL": "XSL"}


def execute(filters=None):
    filters = filters or {}
    now = getdate(today())
    month = _BULAN_ID.index(filters.get("bulan")) + 1 if filters.get("bulan") in _BULAN_ID else now.month
    year = int(filters.get("tahun") or now.year)
    dept_label = filters.get("departemen") or "F&H.S"
    wh = _KATEGORI_DEPT_WAREHOUSE.get(_DEPARTEMEN.get(dept_label, "FASHION"))
    cutoff = now.day if (year, month) == (now.year, now.month) else None
    m1, y1 = (month - 1, year) if month > 1 else (12, year - 1)
    start, end = _period(year, month, cutoff)
    lm_start, lm_end = _period(y1, m1, cutoff)

    live = []

    def sales(s, e, label):
        snap = load_category_sales(s, e, wh)
        if snap is None:
            live.append(label)
            return _category_sales_by_warehouse(s, e, wh)
        return snap

    cur = sales(start, end, f"{_BULAN_ID[month - 1]} {year}")
    lm = sales(lm_start, lm_end, f"{_BULAN_ID[m1 - 1]} {y1}")
    lm = {k: v for k, v in lm.items() if k in cur}  # baris = kategori bulan ini (spt file)
    tot, tot_lm = sum(v["amount"] for v in cur.values()), sum(v["amount"] for v in lm.values())

    data = []
    for cat in sorted(cur):
        c, p = cur[cat], lm.get(cat, {"qty": 0, "amount": 0})
        k, k_lm = (c["amount"] / tot if tot else 0), (p["amount"] / tot_lm if tot_lm else 0)
        data.append({"kategori": cat, "qty": c["qty"], "sales": c["amount"], "kontribusi": k * 100,
                     "qty_lm": p["qty"], "sales_lm": p["amount"], "kontribusi_lm": k_lm * 100,
                     "growth_lm": ((k - k_lm) / k_lm * 100) if k_lm else 0})
    data.append({"kategori": "Grand Total", "bold": 1, "qty": sum(v["qty"] for v in cur.values()), "sales": tot,
                 "kontribusi": 100 if tot else 0, "qty_lm": sum(v["qty"] for v in lm.values()), "sales_lm": tot_lm,
                 "kontribusi_lm": 100 if tot_lm else 0, "growth_lm": 0})
    for r in data:
        for k in ("kontribusi", "kontribusi_lm", "growth_lm"):
            r[k] = round(r[k], 6)

    info = (f"{dept_label}  |  {_BULAN_ID[month - 1]} {year} tgl 1-{end.day} vs {_BULAN_ID[m1 - 1]} {y1} tgl 1-{lm_end.day}"
            f"  |  tahun lalu tdk tersedia (data per item di ERP mulai akhir April 2026)")
    if live:
        info += f"  |  (live: {', '.join(live)})"
    data.insert(0, {"kategori": info, "bold": 1, "is_info": 1})
    return get_columns(month, year, m1, y1), data


def get_columns(month, year, m1, y1):
    def col(fieldname, label, fieldtype="Float", width=130, precision=0):
        c = {"fieldname": fieldname, "label": label, "fieldtype": fieldtype, "width": width}
        if precision is not None:
            c["precision"] = precision
        return c
    cur, lm = f"{_BULAN_ID[month - 1].upper()} {year}", f"{_BULAN_ID[m1 - 1].upper()} {y1}"
    return [
        col("kategori", _("CATEGORY"), "Data", 220, None),
        col("qty", f"{cur} Sum of Qty Terjual", width=120), col("sales", f"{cur} Sum of Sales (Rp)", width=150),
        col("kontribusi", f"{cur} Sum of Kontribusi (%)", "Percent", 120, 2),
        col("qty_lm", f"{lm} Sum of Qty Terjual", width=120), col("sales_lm", f"{lm} Sum of Sales (Rp)", width=150),
        col("kontribusi_lm", f"{lm} Sum of Kontribusi (%)", "Percent", 120, 2),
        col("growth_lm", _("VS LAST MONTH"), "Percent", 120, 2),
    ]
