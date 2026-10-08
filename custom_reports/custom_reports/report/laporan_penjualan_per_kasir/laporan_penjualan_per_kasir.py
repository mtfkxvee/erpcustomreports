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

    # Ambil MOP yang aktif di periode ini
    mop_list = get_active_mop(filters)
    columns  = get_columns(mop_list)
    data     = get_data(filters, mop_list)
    chart    = get_chart(data)
    summary  = get_summary(data)
    return columns, data, None, chart, summary


def get_active_mop(filters):
    conditions = ["si.docstatus = 1", "si.is_return = 0"]
    values = {}
    conditions.append("si.posting_date BETWEEN %(from_date)s AND %(to_date)s")
    values["from_date"] = filters["from_date"]
    values["to_date"]   = filters["to_date"]

    outlet_list = get_outlet_list(filters)
    if outlet_list:
        out_str = "({})".format(", ".join(["'{}'".format(o.replace("'","''")) for o in outlet_list]))
        conditions.append("si.custom_outlet IN {}".format(out_str))

    where = "WHERE " + " AND ".join(conditions)
    sql = (
        "SELECT DISTINCT sip.mode_of_payment"
        " FROM `tabSales Invoice Payment` sip"
        " JOIN `tabSales Invoice` si ON si.name = sip.parent"
        " {where}"
        " ORDER BY sip.mode_of_payment"
    ).format(where=where)

    rows = frappe.db.sql(sql, values, as_dict=True)
    return [r["mode_of_payment"] for r in rows]


def get_columns(mop_list):
    cols = [
        {"fieldname": "kasir",           "label": _("Kasir"),           "fieldtype": "Data",     "width": 200},
        {"fieldname": "sales",           "label": _("Sales (Rp)"),      "fieldtype": "Currency", "width": 160},
        {"fieldname": "total_transaksi", "label": _("Total Transaksi"),  "fieldtype": "Int",      "width": 130},
        {"fieldname": "atv",             "label": _("ATV (Rp)"),        "fieldtype": "Currency", "width": 140},
    ]
    for mop in mop_list:
        mop_key = "mop_" + mop.replace(" ", "_").replace("-", "_").lower()
        cols.append({
            "fieldname": mop_key,
            "label": mop,
            "fieldtype": "Currency",
            "width": 130,
        })
    return cols


def get_data(filters, mop_list):
    conditions = ["si.docstatus = 1", "si.is_return = 0"]
    values = {}
    conditions.append("si.posting_date BETWEEN %(from_date)s AND %(to_date)s")
    values["from_date"] = filters["from_date"]
    values["to_date"]   = filters["to_date"]

    outlet_list = get_outlet_list(filters)
    if outlet_list:
        out_str = "({})".format(", ".join(["'{}'".format(o.replace("'","''")) for o in outlet_list]))
        conditions.append("si.custom_outlet IN {}".format(out_str))

    if filters.get("kasir"):
        conditions.append("si.owner = %(kasir)s")
        values["kasir"] = filters["kasir"]

    where = "WHERE " + " AND ".join(conditions)

    # Query utama: sales & transaksi per kasir
    sql_main = (
        "SELECT si.owner AS kasir,"
        " SUM(si.grand_total - COALESCE(si.loyalty_amount, 0)) AS sales,"
        " COUNT(si.name) AS total_transaksi"
        " FROM `tabSales Invoice` si"
        " {where}"
        " GROUP BY si.owner"
        " ORDER BY sales DESC"
    ).format(where=where)

    # Query MOP per kasir
    sql_mop = (
        "SELECT si.owner AS kasir,"
        " sip.mode_of_payment,"
        " SUM(sip.amount) AS amount"
        " FROM `tabSales Invoice Payment` sip"
        " JOIN `tabSales Invoice` si ON si.name = sip.parent"
        " {where}"
        " GROUP BY si.owner, sip.mode_of_payment"
    ).format(where=where)

    main_rows = frappe.db.sql(sql_main, values, as_dict=True)
    mop_rows  = frappe.db.sql(sql_mop,  values, as_dict=True)

    # Build MOP map per kasir
    mop_map = {}
    for r in mop_rows:
        kasir = r["kasir"]
        mop   = r["mode_of_payment"]
        mop_key = "mop_" + mop.replace(" ", "_").replace("-", "_").lower()
        if kasir not in mop_map:
            mop_map[kasir] = {}
        mop_map[kasir][mop_key] = flt(r["amount"])

    # Ambil full name user
    user_names = list(set(r["kasir"] for r in main_rows))
    user_map = {}
    if user_names:
        fmt = ", ".join(["'{}'".format(u.replace("'","''")) for u in user_names])
        user_rows = frappe.db.sql(
            "SELECT name, full_name FROM `tabUser` WHERE name IN ({})".format(fmt),
            as_dict=True
        )
        user_map = {u["name"]: u["full_name"] or u["name"] for u in user_rows}

    rows = []
    grand_sales = 0
    grand_trx   = 0
    grand_mop   = {}

    for r in main_rows:
        kasir           = r["kasir"]
        sales           = flt(r["sales"])
        total_transaksi = int(r["total_transaksi"])
        atv = sales / total_transaksi if total_transaksi > 0 else 0

        grand_sales += sales
        grand_trx   += total_transaksi

        row = {
            "kasir":           user_map.get(kasir, kasir),
            "sales":           sales,
            "total_transaksi": total_transaksi,
            "atv":             atv,
        }

        # Isi kolom MOP
        kasir_mop = mop_map.get(kasir, {})
        for mop in mop_list:
            mop_key = "mop_" + mop.replace(" ", "_").replace("-", "_").lower()
            val = flt(kasir_mop.get(mop_key, 0))
            row[mop_key] = val
            grand_mop[mop_key] = grand_mop.get(mop_key, 0) + val

        rows.append(row)

    # Baris total
    if rows:
        grand_atv = grand_sales / grand_trx if grand_trx > 0 else 0
        total_row = {
            "kasir":           "<b>TOTAL ({} kasir)</b>".format(len(rows)),
            "sales":           grand_sales,
            "total_transaksi": grand_trx,
            "atv":             grand_atv,
        }
        for mop in mop_list:
            mop_key = "mop_" + mop.replace(" ", "_").replace("-", "_").lower()
            total_row[mop_key] = grand_mop.get(mop_key, 0)
        rows.append(total_row)

    return rows


def get_chart(data):
    if not data or len(data) <= 1:
        return None
    chart_data = [r for r in data if not str(r.get("kasir","")).startswith("<b>")][:10]
    labels     = [r["kasir"] for r in chart_data]
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
    return [
        {"value": total["sales"],           "label": "Total Sales",     "datatype": "Currency", "indicator": "green"},
        {"value": total["total_transaksi"],  "label": "Total Transaksi", "datatype": "Int",      "indicator": "blue"},
        {"value": total["atv"],             "label": "ATV",             "datatype": "Currency", "indicator": "orange"},
        {"value": len(data) - 1,            "label": "Jumlah Kasir",    "datatype": "Int",      "indicator": "purple"},
    ]
