# Copyright (c) 2026, X-SHA and contributors
# For license information, please see license.txt
#
# Laporan "Sales YTD" - tampilan ERP dari file admin "SALES X-SHA GROUP_YTD_ 2026":
# 1 sheet (filter Sheet) = baris Januari-Desember + TOTAL + kuartal Q1-Q4,
# kolom per tahun TARGET, SALES, ACH, GROWTH (vs tahun sebelumnya), kontribusi
# (sales bulan / sales setahun). Sumber angka & aturan lihat custom_reports/sales_ytd.py.

from frappe import _
from frappe.utils import getdate, today

from custom_reports.sales_ytd import YTD, build_sheet, has_kontribusi, sheet_meta


def execute(filters=None):
    filters = filters or {}
    order, titles = sheet_meta()
    kode = filters.get("sheet") if filters.get("sheet") in order else "TOTAL"
    upto = int(filters.get("tahun") or getdate(today()).year)
    sheet = build_sheet(YTD(), kode, upto)
    years = sheet["years"]

    def row(item, bold=0):
        r = {"bulan": item["label"], "bold": bold}
        for y in years:
            c = item["per_year"][y]
            r.update({f"t_{y}": c["target"], f"s_{y}": c["sales"], f"a_{y}": c["ach"], f"g_{y}": c["growth"],
                      f"k_{y}": c["kontribusi"]})
        return r

    data = [row(m) for m in sheet["months"]]
    data.append(row(sheet["total"], bold=1))
    data.append({})
    data.append({"bulan": "KUARTAL", "bold": 1, "is_header": 1})
    data += [row(q) for q in sheet["quarters"]]
    data.append(row(sheet["total"], bold=1))

    info = f"{titles.get(kode, kode)}"
    if sheet["open"]:
        info += "  |  dihitung live dari ERP (blm dibekukan): " + ", ".join(f"{m:02d}/{y}" for y, m in sheet["open"])
    data.insert(0, {"bulan": info, "bold": 1, "is_info": 1})
    return get_columns(years), data


def get_columns(years):
    def col(fieldname, label, fieldtype="Float", width=130, precision=0):
        c = {"fieldname": fieldname, "label": label, "fieldtype": fieldtype, "width": width}
        if precision is not None:
            c["precision"] = precision
        return c
    cols = [col("bulan", _("MONTH"), "Data", 120, None)]
    for i, y in enumerate(years):
        cols += [col(f"t_{y}", f"{y} TARGET", width=135), col(f"s_{y}", f"{y} SALES", width=135),
                 col(f"a_{y}", f"{y} ACH", "Percent", 80, 1)]
        if i:
            cols.append(col(f"g_{y}", f"{y} GROWTH", "Percent", 85, 2))
        if has_kontribusi(years, y):
            cols.append(col(f"k_{y}", f"{y} kontribusi", "Percent", 90, 2))
    return cols
