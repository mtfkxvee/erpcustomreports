# Copyright (c) 2026, X-SHA and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt

from custom_reports.custom_reports.report.laporan_penjualan_per_kasir.laporan_penjualan_per_kasir import (
    get_outlet_list,
)


def execute(filters=None):
    filters = frappe._dict(filters or {})
    if not filters.get("from_date") or not filters.get("to_date"):
        frappe.msgprint(
            "Silakan pilih <b>Dari Tanggal</b> dan <b>Sampai Tanggal</b> terlebih dahulu.",
            indicator="orange", alert=True
        )
        return [], []

    data = get_data(filters)
    return get_columns(), data, None, get_chart(data), get_summary(data)


def get_columns():
    return [
        {"fieldname": "posting_date",    "label": _("Tanggal"),          "fieldtype": "Date",     "width": 100},
        {"fieldname": "invoice",         "label": _("Sales Invoice"),    "fieldtype": "Link",     "options": "Sales Invoice", "width": 180},
        {"fieldname": "outlet",          "label": _("Outlet"),           "fieldtype": "Link",     "options": "Outlet", "width": 100},
        {"fieldname": "kasir",           "label": _("Kasir"),            "fieldtype": "Data",     "width": 160},
        {"fieldname": "customer",        "label": _("Customer"),         "fieldtype": "Link",     "options": "Customer", "width": 110},
        {"fieldname": "customer_name",   "label": _("Nama Customer"),    "fieldtype": "Data",     "width": 180},
        {"fieldname": "coupon",          "label": _("Kupon"),            "fieldtype": "Link",     "options": "POS Coupon", "width": 130},
        {"fieldname": "coupon_type",     "label": _("Tipe Kupon"),       "fieldtype": "Data",     "width": 100},
        {"fieldname": "discount_type",   "label": _("Jenis Diskon"),     "fieldtype": "Data",     "width": 100},
        {"fieldname": "discount_percentage", "label": _("Persentase Kupon (%)"), "fieldtype": "Percent",  "width": 130},
        {"fieldname": "discount_amount", "label": _("Nominal Kupon (Rp)"), "fieldtype": "Currency", "width": 140},
        {"fieldname": "min_amount",      "label": _("Min. Belanja (Rp)"),  "fieldtype": "Currency", "width": 140},
        {"fieldname": "max_amount",      "label": _("Maks. Potongan (Rp)"), "fieldtype": "Currency", "width": 150},
        {"fieldname": "total_qty",       "label": _("Qty"),              "fieldtype": "Float",    "width": 70},
        {"fieldname": "subtotal",        "label": _("Subtotal (Rp)"),    "fieldtype": "Currency", "width": 130},
        {"fieldname": "coupon_discount", "label": _("Potongan Kupon (Rp)"), "fieldtype": "Currency", "width": 150},
        {"fieldname": "grand_total",     "label": _("Grand Total (Rp)"), "fieldtype": "Currency", "width": 140},
    ]


def get_data(filters):
    conditions = [
        "si.docstatus = 1",
        "si.is_return = 0",
        "IFNULL(si.custom_pos_coupon, '') != ''",
        "si.posting_date BETWEEN %(from_date)s AND %(to_date)s",
    ]
    values = {"from_date": filters.from_date, "to_date": filters.to_date}

    outlet_list = get_outlet_list(filters)
    if outlet_list:
        conditions.append("si.custom_outlet IN %(outlets)s")
        values["outlets"] = tuple(outlet_list)

    if filters.get("coupon"):
        conditions.append("si.custom_pos_coupon = %(coupon)s")
        values["coupon"] = filters.coupon

    if filters.get("customer"):
        conditions.append("si.customer = %(customer)s")
        values["customer"] = filters.customer

    if filters.get("kasir"):
        conditions.append("si.owner = %(kasir)s")
        values["kasir"] = filters.kasir

    rows = frappe.db.sql(
        """
        SELECT
            si.posting_date,
            si.name AS invoice,
            si.custom_outlet AS outlet,
            COALESCE(u.full_name, si.owner) AS kasir,
            si.customer,
            si.customer_name,
            si.custom_pos_coupon AS coupon,
            pc.coupon_type,
            pc.discount_type,
            pc.discount_percentage,
            pc.discount_amount,
            pc.min_amount,
            pc.max_amount,
            si.total_qty,
            si.total AS subtotal,
            si.custom_coupon_discount_amount AS coupon_discount,
            si.grand_total
        FROM `tabSales Invoice` si
        LEFT JOIN `tabPOS Coupon` pc ON pc.name = si.custom_pos_coupon
        LEFT JOIN `tabUser` u ON u.name = si.owner
        WHERE {where}
        ORDER BY si.posting_date DESC, si.posting_time DESC
        """.format(where=" AND ".join(conditions)),
        values,
        as_dict=True,
    )

    if rows:
        rows.append({
            "posting_date": None,
            "invoice": "<b>TOTAL ({} invoice)</b>".format(len(rows)),
            "total_qty": sum(flt(r.total_qty) for r in rows),
            "subtotal": sum(flt(r.subtotal) for r in rows),
            "coupon_discount": sum(flt(r.coupon_discount) for r in rows),
            "grand_total": sum(flt(r.grand_total) for r in rows),
        })
    return rows


def get_chart(data):
    if len(data) <= 1:
        return None

    per_coupon = {}
    for r in data[:-1]:
        c = per_coupon.setdefault(r["coupon"], {"discount": 0, "count": 0})
        c["discount"] += flt(r["coupon_discount"])
        c["count"] += 1

    top = sorted(per_coupon.items(), key=lambda kv: kv[1]["discount"], reverse=True)[:10]
    return {
        "data": {
            "labels": [k for k, _v in top],
            "datasets": [
                {"name": "Potongan Kupon (Rp)", "values": [v["discount"] for _k, v in top], "chartType": "bar"},
                {"name": "Jumlah Pakai", "values": [v["count"] for _k, v in top], "chartType": "line"},
            ],
        },
        "type": "axis-mixed",
        "fieldtype": "Currency",
        "colors": ["#5E64FF", "#FF5E5E"],
        "axisOptions": {"xIsSeries": 1},
        "height": 300,
    }


def get_summary(data):
    if not data:
        return None
    total = data[-1]
    jumlah = len(data) - 1
    kupon_unik = len({r["coupon"] for r in data[:-1]})
    return [
        {"value": total["coupon_discount"], "label": "Total Potongan Kupon", "datatype": "Currency", "indicator": "red"},
        {"value": jumlah,                   "label": "Invoice Pakai Kupon",  "datatype": "Int",      "indicator": "blue"},
        {"value": kupon_unik,               "label": "Kupon Berbeda",        "datatype": "Int",      "indicator": "purple"},
        {"value": total["grand_total"],     "label": "Total Penjualan",      "datatype": "Currency", "indicator": "green"},
    ]
