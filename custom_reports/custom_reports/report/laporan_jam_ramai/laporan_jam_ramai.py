import frappe
from frappe import _
from frappe.utils import flt


def get_outlet_children(outlet):
    result = []
    queue = [outlet]
    while queue:
        current = queue.pop(0)
        o = frappe.db.get_value("Outlet", current, ["is_group", "name"], as_dict=True)
        if not o:
            continue
        if not o.is_group:
            result.append(current)
        else:
            children = frappe.db.get_all("Outlet", filters={"parent_outlet": current}, fields=["name", "is_group"])
            for c in children:
                queue.append(c["name"])
    return result if result else [outlet]


def get_outlet_list(filters):
    outlet_raw = filters.get("outlet")
    if not outlet_raw:
        return []
    if isinstance(outlet_raw, list):
        outlets = []
        for o in outlet_raw:
            if isinstance(o, dict):
                outlets.append(o.get("value") or o.get("name") or "")
            else:
                outlets.append(str(o))
        outlets = [o for o in outlets if o]
    else:
        outlets = [str(outlet_raw)]
    result = []
    for o in outlets:
        children = get_outlet_children(o)
        for c in children:
            if c not in result:
                result.append(c)
    return result


def execute(filters=None):
    if not filters:
        filters = {}
    if not filters.get("from_date") or not filters.get("to_date"):
        frappe.msgprint(
            "Silakan pilih <b>Dari Tanggal</b> dan <b>Sampai Tanggal</b> terlebih dahulu.",
            indicator="orange", alert=True
        )
        return [], []
    columns = get_columns()
    data    = get_data(filters)
    chart   = get_chart(data)
    summary = get_summary(data)
    return columns, data, None, chart, summary


def get_columns():
    return [
        {"fieldname": "jam",             "label": _("Jam"),             "fieldtype": "Data",     "width": 80},
        {"fieldname": "sales",           "label": _("Sales (Rp)"),      "fieldtype": "Currency", "width": 160},
        {"fieldname": "total_transaksi", "label": _("Total Transaksi"),  "fieldtype": "Int",      "width": 130},
        {"fieldname": "atv",             "label": _("ATV (Rp)"),        "fieldtype": "Currency", "width": 140},
    ]


def get_data(filters):
    conditions = ["si.docstatus = 1", "si.is_return = 0"]
    values = {}
    conditions.append("si.posting_date BETWEEN %(from_date)s AND %(to_date)s")
    values["from_date"] = filters["from_date"]
    values["to_date"]   = filters["to_date"]

    outlet_list = get_outlet_list(filters)
    if outlet_list:
        if len(outlet_list) == 1:
            conditions.append("si.custom_outlet = %(outlet)s")
            values["outlet"] = outlet_list[0]
        else:
            out_str = "({})".format(", ".join(["'{}'".format(o.replace("'","''")) for o in outlet_list]))
            conditions.append("si.custom_outlet IN {}".format(out_str))

    where = "WHERE " + " AND ".join(conditions)

    sql = (
        "SELECT HOUR(si.posting_time) AS hour_num,"
        " SUM(si.grand_total - COALESCE(si.loyalty_amount, 0)) AS sales,"
        " COUNT(si.name) AS total_transaksi"
        " FROM `tabSales Invoice` si"
        " {where}"
        " GROUP BY HOUR(si.posting_time)"
        " ORDER BY HOUR(si.posting_time) ASC"
    ).format(where=where)

    raw = frappe.db.sql(sql, values, as_dict=True)

    # Build map dari hasil query
    hour_map = {}
    for r in raw:
        hour_map[int(r["hour_num"])] = {
            "sales":           flt(r["sales"]),
            "total_transaksi": int(r["total_transaksi"]),
        }

    rows = []
    grand_sales = 0
    grand_transaksi = 0

    # Tampilkan jam 00:00 - 23:00 semua (yang tidak ada transaksi = 0)
    for h in range(24):
        d = hour_map.get(h, {"sales": 0, "total_transaksi": 0})
        sales           = d["sales"]
        total_transaksi = d["total_transaksi"]
        atv = sales / total_transaksi if total_transaksi > 0 else 0
        grand_sales     += sales
        grand_transaksi += total_transaksi
        rows.append({
            "jam":             "{:02d}:00 - {:02d}:59".format(h, h),
            "sales":           sales,
            "total_transaksi": total_transaksi,
            "atv":             atv,
        })

    if rows:
        grand_atv = grand_sales / grand_transaksi if grand_transaksi > 0 else 0
        rows.append({
            "jam":             "<b>TOTAL</b>",
            "sales":           grand_sales,
            "total_transaksi": grand_transaksi,
            "atv":             grand_atv,
        })

    return rows


def get_chart(data):
    if not data or len(data) <= 1:
        return None
    chart_data = [r for r in data if r.get("jam") != "<b>TOTAL</b>"]
    labels     = [r["jam"] for r in chart_data]
    sales_vals = [flt(r["sales"]) for r in chart_data]
    trx_vals   = [int(r["total_transaksi"]) for r in chart_data]
    return {
        "data": {
            "labels": labels,
            "datasets": [
                {"name": "Sales (Rp)",  "values": sales_vals, "chartType": "bar"},
                {"name": "Transaksi",   "values": trx_vals,   "chartType": "line"},
            ]
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
    # Cari jam tersibuk
    chart_data = [r for r in data if r.get("jam") != "<b>TOTAL</b>"]
    jam_tersibuk = max(chart_data, key=lambda x: x["total_transaksi"]) if chart_data else {}
    jam_terlaris = max(chart_data, key=lambda x: x["sales"]) if chart_data else {}
    return [
        {"value": total["sales"],           "label": "Total Sales",       "datatype": "Currency", "indicator": "green"},
        {"value": total["total_transaksi"],  "label": "Total Transaksi",   "datatype": "Int",      "indicator": "blue"},
        {"value": total["atv"],             "label": "ATV",               "datatype": "Currency", "indicator": "orange"},
        {"value": jam_tersibuk.get("jam",""), "label": "Jam Tersibuk",    "datatype": "Data",     "indicator": "red"},
    ]
