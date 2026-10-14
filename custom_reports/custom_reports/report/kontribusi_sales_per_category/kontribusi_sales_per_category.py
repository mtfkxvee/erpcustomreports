# Copyright (c) 2026, X-SHA and contributors
# For license information, please see license.txt
#
# Laporan "Kontribusi Sales per Category" - tampilan ERP dari file "KONTRIBUSI
# SALES CATEGORY W4 VS W3" (sheet F&H.S / FMCG / XSL; sheet MBG tdk dibuat).
# Rumus = API sales_api.get_kontribusi_sales_category (_kontribusi_category):
#   Qty & Sales  = SUM(qty) & SUM(base_net_amount) Sales Invoice (non-retur) di
#                  warehouse group departemen, per field Category master Item
#   Kontribusi   = sales kategori / grand total minggu itu
#   Growth       = (kontribusi minggu ini - minggu lalu) / minggu lalu (0 kalau
#                  minggu lalu 0, spt IFERROR di file)
# Minggu = blok 1-7 / 8-14 / 15-21 / 22-akhir; W1 dibandingkan W4 bulan lalu.
# Data dibaca dari snapshot harian (sales_snapshot.load_category_sales) kalau
# lengkap, kalau tidak live + label "(live)".

import frappe
from frappe import _
from frappe.utils import formatdate, getdate

from custom_reports.sales_api import _category_sales_by_warehouse, _kontribusi_category
from custom_reports.sales_snapshot import load_category_sales

_BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli",
          "Agustus", "September", "Oktober", "November", "Desember"]
_DEPARTEMEN = {"F&H.S": "FASHION", "FMCG": "FMCG", "XSL": "XSL"}


def execute(filters=None):
    filters = filters or {}
    month = _BULAN.index(filters.get("bulan") or _BULAN[getdate().month - 1]) + 1
    year = int(filters.get("tahun") or getdate().year)
    week_idx = int(str(filters.get("minggu") or "W4").upper().lstrip("W")) - 1
    if week_idx not in range(4):
        frappe.throw(_("Minggu harus W1 - W4"))
    dept = _DEPARTEMEN.get(filters.get("departemen") or "F&H.S", "FASHION")

    live = []

    def sales_fn(start, end, warehouse_group):
        snap = load_category_sales(start, end, warehouse_group)
        if snap is None:
            live.append(start)
            return _category_sales_by_warehouse(start, end, warehouse_group)
        return snap

    res = _kontribusi_category(dept, year, month, week_idx, sales_fn=sales_fn)
    cur, prev = res["week_current"], res["week_previous"]

    data = []
    for r in res["rows"]:
        data.append({
            "kategori": r["category"],
            "qty": r["week_current"]["qty"], "sales": r["week_current"]["sales"],
            "kontribusi": r["week_current"]["kontribusi_pct"],
            "qty_prev": r["week_previous"]["qty"], "sales_prev": r["week_previous"]["sales"],
            "kontribusi_prev": r["week_previous"]["kontribusi_pct"],
            "growth": r["growth_kontribusi_pct"],
        })
    data.append({
        "kategori": "Grand Total", "bold": 1,
        "qty": cur["total_qty"], "sales": cur["total_sales"], "kontribusi": 100 if cur["total_sales"] else 0,
        "qty_prev": prev["total_qty"], "sales_prev": prev["total_sales"],
        "kontribusi_prev": 100 if prev["total_sales"] else 0, "growth": 0,
    })

    def periode(w):
        s, e = getdate(w["start"]), getdate(w["end"])
        return f"W{w['week_no']} {formatdate(s, 'dd')}-{formatdate(e, 'dd MMMM yyyy')}"

    info = f"{filters.get('departemen') or 'F&H.S'}  |  {periode(cur)} vs {periode(prev)}"
    if live:
        lives = ["minggu ini" if str(s) == cur["start"] else "minggu lalu" for s in live]
        info += f"  |  (live: {', '.join(lives)})"
    data.insert(0, {"kategori": info, "bold": 1, "is_info": 1})
    return get_columns(cur["week_no"], prev["week_no"]), data


def get_columns(week_no=4, prev_week_no=3):
    def col(fieldname, label, fieldtype="Float", width=130, precision=0):
        c = {"fieldname": fieldname, "label": label, "fieldtype": fieldtype, "width": width}
        if precision is not None:
            c["precision"] = precision
        return c
    w, p = f"WEEK-{week_no}", f"WEEK-{prev_week_no}"
    return [
        col("kategori", _("Row Labels"), "Data", 220, None),
        col("qty", f"{w} Sum of Qty Terjual", width=120),
        col("sales", f"{w} Sum of Sales (Rp)", width=150),
        col("kontribusi", f"{w} Sum of Kontribusi (%)", "Percent", 120, 2),
        col("qty_prev", f"{p} Sum of Qty Terjual", width=120),
        col("sales_prev", f"{p} Sum of Sales (Rp)", width=150),
        col("kontribusi_prev", f"{p} Sum of Kontribusi (%)", "Percent", 120, 2),
        col("growth", f"GROWTH W{week_no} VS W{prev_week_no} Kontribusi (%)", "Percent", 140, 2),
    ]
