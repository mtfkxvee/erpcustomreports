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


def get_customer_group_children(customer_group):
    """Ambil semua child customer group rekursif."""
    result = []
    queue = [customer_group]
    while queue:
        current = queue.pop(0)
        cg = frappe.db.get_value("Customer Group", current, ["is_group", "name"], as_dict=True)
        if not cg:
            continue
        if not cg.is_group:
            result.append(current)
        else:
            result.append(current)
            children = frappe.db.get_all("Customer Group", filters={"parent_customer_group": current}, fields=["name", "is_group"])
            for c in children:
                queue.append(c["name"])
    return result if result else [customer_group]


def execute(filters=None):
    if not filters:
        filters = {}
    if not filters.get("from_date") or not filters.get("to_date"):
        frappe.msgprint(
            "Silakan pilih <b>Dari Tanggal</b> dan <b>Sampai Tanggal</b> terlebih dahulu.",
            indicator="orange", alert=True
        )
        return [], []
    mode = filters.get("mode") or "Per Pelanggan"
    columns = get_columns(mode)
    data    = get_data(filters, mode)
    chart   = get_chart(data, mode)
    summary = get_summary(data)
    return columns, data, None, chart, summary


def get_columns(mode):
    if mode == "Per Group Pelanggan":
        first_col = {"fieldname": "customer_group", "label": _("Group Pelanggan"), "fieldtype": "Link", "options": "Customer Group", "width": 180}
        second_col = None
    else:
        first_col  = {"fieldname": "customer",      "label": _("Pelanggan"),       "fieldtype": "Link", "options": "Customer",       "width": 180}
        second_col = {"fieldname": "customer_name",  "label": _("Nama Pelanggan"),  "fieldtype": "Data",                              "width": 180}

    cols = [first_col]
    if second_col:
        cols.append(second_col)
    cols += [
        {"fieldname": "sales",           "label": _("Sales (Rp)"),       "fieldtype": "Currency", "width": 160},
        {"fieldname": "total_transaksi", "label": _("Total Transaksi"),   "fieldtype": "Int",      "width": 130},
        {"fieldname": "atv",             "label": _("ATV (Rp)"),         "fieldtype": "Currency", "width": 140},
        {"fieldname": "total_item",      "label": _("Item Terjual"),     "fieldtype": "Int",      "width": 120},
        {"fieldname": "total_qty",       "label": _("Qty Item Terjual"), "fieldtype": "Float",    "width": 130},
    ]
    return cols


def build_where(filters, mode):
    conditions = ["si.docstatus = 1", "si.is_return = 0"]
    values = {}
    conditions.append("si.posting_date BETWEEN %(from_date)s AND %(to_date)s")
    values["from_date"] = filters["from_date"]
    values["to_date"]   = filters["to_date"]

    # Outlet filter
    outlet_list = get_outlet_list(filters)
    if outlet_list:
        if len(outlet_list) == 1:
            conditions.append("si.custom_outlet = %(outlet)s")
            values["outlet"] = outlet_list[0]
        else:
            out_str = "({})".format(", ".join(["'{}'".format(o.replace("'","''")) for o in outlet_list]))
            conditions.append("si.custom_outlet IN {}".format(out_str))

    # Customer filter
    if mode == "Per Pelanggan" and filters.get("customer"):
        conditions.append("si.customer = %(customer)s")
        values["customer"] = filters["customer"]

    # Customer group filter (expand children)
    if mode == "Per Group Pelanggan" and filters.get("customer_group"):
        cg_list = get_customer_group_children(filters["customer_group"])
        if len(cg_list) == 1:
            conditions.append("si.customer_group = %(customer_group)s")
            values["customer_group"] = cg_list[0]
        else:
            cg_str = "({})".format(", ".join(["'{}'".format(c.replace("'","''")) for c in cg_list]))
            conditions.append("si.customer_group IN {}".format(cg_str))

    return "WHERE " + " AND ".join(conditions), values


def get_data(filters, mode):
    where, values = build_where(filters, mode)

    if mode == "Per Group Pelanggan":
        group_field = "si.customer_group"
        group_alias = "customer_group"
    else:
        group_field = "si.customer"
        group_alias = "customer"

    sql_main = (
        "SELECT {group_field} AS {group_alias},"
        + (" si.customer_name," if mode == "Per Pelanggan" else "")
        + " SUM(si.grand_total - COALESCE(si.loyalty_amount, 0)) AS sales,"
        " COUNT(si.name) AS total_transaksi"
        " FROM `tabSales Invoice` si"
        " {where}"
        " GROUP BY {group_field}"
        " ORDER BY sales DESC"
    ).format(group_field=group_field, group_alias=group_alias, where=where)

    sql_item = (
        "SELECT {group_field} AS {group_alias},"
        " COUNT(DISTINCT sii.item_code) AS total_item,"
        " SUM(sii.qty) AS total_qty"
        " FROM `tabSales Invoice Item` sii"
        " JOIN `tabSales Invoice` si ON si.name = sii.parent"
        " {where}"
        " GROUP BY {group_field}"
    ).format(group_field=group_field, group_alias=group_alias, where=where)

    main_rows = frappe.db.sql(sql_main, values, as_dict=True)
    item_rows  = frappe.db.sql(sql_item,  values, as_dict=True)

    item_map = {}
    for r in item_rows:
        item_map[r[group_alias]] = {
            "total_item": int(r["total_item"] or 0),
            "total_qty":  flt(r["total_qty"] or 0),
        }

    rows = []
    grand_sales = 0
    grand_transaksi = 0
    grand_item = 0
    grand_qty = 0

    for r in main_rows:
        key = r[group_alias]
        im  = item_map.get(key, {})
        sales           = flt(r["sales"])
        total_transaksi = int(r["total_transaksi"])
        total_item      = im.get("total_item", 0)
        total_qty       = im.get("total_qty", 0)
        atv = sales / total_transaksi if total_transaksi > 0 else 0

        grand_sales     += sales
        grand_transaksi += total_transaksi
        grand_item      += total_item
        grand_qty       += total_qty

        row = {
            group_alias:       key,
            "sales":           sales,
            "total_transaksi": total_transaksi,
            "atv":             atv,
            "total_item":      total_item,
            "total_qty":       total_qty,
        }
        if mode == "Per Pelanggan":
            row["customer_name"] = r.get("customer_name") or key

        rows.append(row)

    if rows:
        grand_atv = grand_sales / grand_transaksi if grand_transaksi > 0 else 0
        total_row = {
            group_alias:       "<b>TOTAL ({} baris)</b>".format(len(rows)),
            "sales":           grand_sales,
            "total_transaksi": grand_transaksi,
            "atv":             grand_atv,
            "total_item":      grand_item,
            "total_qty":       grand_qty,
        }
        if mode == "Per Pelanggan":
            total_row["customer_name"] = None
        rows.append(total_row)

    return rows


def get_chart(data, mode):
    if not data or len(data) <= 1:
        return None
    chart_data = data[:-1][:10]  # Top 10, exclude total
    if mode == "Per Group Pelanggan":
        labels = [r.get("customer_group", "") or "" for r in chart_data]
    else:
        labels = [r.get("customer_name") or r.get("customer", "") for r in chart_data]
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
        {"value": total["sales"],           "label": "Total Sales",      "datatype": "Currency", "indicator": "green"},
        {"value": total["total_transaksi"],  "label": "Total Transaksi",  "datatype": "Int",      "indicator": "blue"},
        {"value": total["atv"],             "label": "ATV",              "datatype": "Currency", "indicator": "orange"},
        {"value": total["total_qty"],       "label": "Total Qty Terjual","datatype": "Float",    "indicator": "purple"},
    ]
