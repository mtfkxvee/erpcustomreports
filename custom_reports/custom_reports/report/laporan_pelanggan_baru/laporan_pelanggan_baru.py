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
    result = []
    queue = [customer_group]
    while queue:
        current = queue.pop(0)
        cg = frappe.db.get_value("Customer Group", current, ["is_group", "name"], as_dict=True)
        if not cg:
            continue
        result.append(current)
        if cg.is_group:
            children = frappe.db.get_all("Customer Group", filters={"parent_customer_group": current}, fields=["name"])
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
    columns = get_columns()
    data    = get_data(filters)
    chart   = get_chart(data)
    summary = get_summary(data)
    return columns, data, None, chart, summary


def get_columns():
    return [
        {"fieldname": "customer",        "label": _("ID Pelanggan"),          "fieldtype": "Link",     "options": "Customer", "width": 150},
        {"fieldname": "customer_name",   "label": _("Nama Pelanggan"),        "fieldtype": "Data",     "width": 200},
        {"fieldname": "customer_group",  "label": _("Group Pelanggan"),       "fieldtype": "Link",     "options": "Customer Group", "width": 150},
        {"fieldname": "tgl_dibuat",      "label": _("Tgl Pelanggan Dibuat"),  "fieldtype": "Date",     "width": 150},
        {"fieldname": "created_by",      "label": _("Dibuat Oleh"),           "fieldtype": "Data",     "width": 180},
        {"fieldname": "sales",           "label": _("Sales (Rp)"),            "fieldtype": "Currency", "width": 160},
        {"fieldname": "total_transaksi", "label": _("Total Transaksi"),        "fieldtype": "Int",      "width": 130},
        {"fieldname": "atv",             "label": _("ATV (Rp)"),              "fieldtype": "Currency", "width": 140},
    ]


def get_data(filters):
    outlet_list = get_outlet_list(filters)
    values = {
        "from_date": filters["from_date"],
        "to_date":   filters["to_date"],
    }

    # Customer group condition
    cg_condition = ""
    if filters.get("customer_group"):
        cg_list = get_customer_group_children(filters["customer_group"])
        if len(cg_list) == 1:
            cg_condition = "AND c.customer_group = %(customer_group)s"
            values["customer_group"] = cg_list[0]
        else:
            cg_str = "({})".format(", ".join(["'{}'".format(c.replace("'","''")) for c in cg_list]))
            cg_condition = "AND c.customer_group IN {}".format(cg_str)

    # Step 1: Ambil semua customer baru berdasarkan tgl creation
    sql_new = (
        "SELECT c.name AS customer, c.customer_name, c.customer_group,"
        " DATE(c.creation) AS tgl_dibuat, c.owner AS created_by"
        " FROM `tabCustomer` c"
        " WHERE DATE(c.creation) BETWEEN %(from_date)s AND %(to_date)s"
        " {cg_condition}"
        " ORDER BY c.creation ASC"
    ).format(cg_condition=cg_condition)

    new_customers = frappe.db.sql(sql_new, values, as_dict=True)
    if not new_customers:
        return []

    customer_list = [r["customer"] for r in new_customers]
    customer_meta = {r["customer"]: r for r in new_customers}

    # Build outlet condition sebagai string langsung (hindari konflik .format vs %(key)s)
    outlet_condition = ""
    if outlet_list:
        if len(outlet_list) == 1:
            outlet_condition = "AND si.custom_outlet = '{}'".format(outlet_list[0].replace("'","''"))
        else:
            out_str = "({})".format(", ".join(["'{}'".format(o.replace("'","''")) for o in outlet_list]))
            outlet_condition = "AND si.custom_outlet IN {}".format(out_str)

    # Step 2: Hitung sales per customer dalam periode, filter per outlet
    cust_str = "({})".format(", ".join(["'{}'".format(c.replace("'","''")) for c in customer_list]))

    sql_sales = (
        "SELECT si.customer,"
        " SUM(si.grand_total - COALESCE(si.loyalty_amount, 0)) AS sales,"
        " COUNT(si.name) AS total_transaksi"
        " FROM `tabSales Invoice` si"
        " WHERE si.docstatus = 1"
        " AND si.is_return = 0"
        " AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s"
        " AND si.customer IN {cust_str}"
        " {outlet_condition}"
        " GROUP BY si.customer"
    ).format(cust_str=cust_str, outlet_condition=outlet_condition)

    sales_rows = frappe.db.sql(sql_sales, values, as_dict=True)
    sales_map  = {r["customer"]: r for r in sales_rows}

    rows = []
    grand_sales = 0
    grand_trx   = 0

    for cust in new_customers:
        c    = cust["customer"]
        meta = customer_meta.get(c, {})
        s    = sales_map.get(c, {})

        sales           = flt(s.get("sales", 0))
        total_transaksi = int(s.get("total_transaksi", 0))

        # Jika ada filter outlet, skip customer yang tidak punya sales di outlet tsb
        if outlet_list and sales == 0:
            continue

        atv = sales / total_transaksi if total_transaksi > 0 else 0
        grand_sales += sales
        grand_trx   += total_transaksi

        rows.append({
            "customer":        c,
            "customer_name":   meta.get("customer_name") or c,
            "customer_group":  meta.get("customer_group"),
            "tgl_dibuat":      meta.get("tgl_dibuat"),
            "created_by":      meta.get("created_by") or "",
            "sales":           sales,
            "total_transaksi": total_transaksi,
            "atv":             atv,
        })

    # Sort by sales DESC
    rows.sort(key=lambda x: x["sales"], reverse=True)

    if rows:
        grand_atv = grand_sales / grand_trx if grand_trx > 0 else 0
        rows.append({
            "customer":        None,
            "customer_name":   "<b>TOTAL ({} pelanggan baru)</b>".format(len(rows)),
            "customer_group":  None,
            "tgl_dibuat":      None,
            "created_by":      None,
            "sales":           grand_sales,
            "total_transaksi": grand_trx,
            "atv":             grand_atv,
        })

    return rows


def get_chart(data):
    if not data or len(data) <= 1:
        return None
    chart_data = [r for r in data if r.get("customer")][:10]
    labels     = [r.get("customer_name") or r.get("customer", "") for r in chart_data]
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
        "height": 280,
    }


def get_summary(data):
    if not data:
        return None
    total = data[-1]
    pelanggan_baru = len(data) - 1
    return [
        {"value": pelanggan_baru,                "label": "Pelanggan Baru",  "datatype": "Int",      "indicator": "blue"},
        {"value": total["sales"],                "label": "Total Sales",     "datatype": "Currency", "indicator": "green"},
        {"value": total["total_transaksi"],       "label": "Total Transaksi", "datatype": "Int",      "indicator": "orange"},
        {"value": total["atv"],                  "label": "ATV",             "datatype": "Currency", "indicator": "purple"},
    ]
