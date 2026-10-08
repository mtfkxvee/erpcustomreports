import frappe
from frappe import _
from frappe.utils import flt


def get_warehouse_children(warehouse):
    wh = frappe.db.get_value("Warehouse", warehouse, ["lft", "rgt", "is_group"], as_dict=True)
    if not wh:
        return [warehouse]
    if not wh.is_group:
        return [warehouse]
    children = frappe.db.sql(
        "SELECT name FROM `tabWarehouse` WHERE lft >= %s AND rgt <= %s AND is_group = 0",
        (wh.lft, wh.rgt), as_dict=True
    )
    return [c["name"] for c in children] if children else [warehouse]


def execute(filters=None):
    if not filters:
        filters = {}
    if not filters.get("from_date") or not filters.get("to_date"):
        frappe.msgprint("Silakan pilih periode.", indicator="orange", alert=True)
        return [], []
    columns = get_columns()
    data    = get_data(filters)
    return columns, data


def get_columns():
    return [
        {"fieldname": "doctype",       "label": _("Tipe Dokumen"),    "fieldtype": "Data",         "width": 160},
        {"fieldname": "name",          "label": _("No. Dokumen"),     "fieldtype": "Dynamic Link", "options": "doctype", "width": 200},
        {"fieldname": "posting_date",  "label": _("Tgl Transaksi"),   "fieldtype": "Date",         "width": 110},
        {"fieldname": "cancelled_on",  "label": _("Tgl Dibatalkan"),  "fieldtype": "Datetime",     "width": 150},
        {"fieldname": "cancelled_by",  "label": _("Dibatalkan Oleh"), "fieldtype": "Data",         "width": 180},
        {"fieldname": "warehouse",     "label": _("Warehouse"),       "fieldtype": "Data",         "width": 180},
        {"fieldname": "grand_total",   "label": _("Nilai (Rp)"),      "fieldtype": "Currency",     "width": 150},
        {"fieldname": "remarks",       "label": _("Keterangan"),      "fieldtype": "Data",         "width": 200},
    ]


def get_data(filters):
    doctype_filter = filters.get("doctype")
    warehouse      = filters.get("warehouse")
    from_date      = filters["from_date"]
    to_date        = filters["to_date"]

    # Expand warehouse ke children
    wh_list = []
    if warehouse:
        wh_list = get_warehouse_children(warehouse)

    doctypes = [doctype_filter] if doctype_filter else [
        "Sales Invoice", "Purchase Invoice", "Purchase Receipt",
        "Stock Entry", "Stock Reconciliation"
    ]

    rows = []
    grand_total_sum = 0

    for dt in doctypes:
        dt_rows = get_cancelled_docs(dt, from_date, to_date, wh_list)
        rows.extend(dt_rows)
        grand_total_sum += sum(flt(r.get("grand_total", 0)) for r in dt_rows)

    # Sort by cancelled_on DESC
    rows.sort(key=lambda x: str(x.get("cancelled_on") or ""), reverse=True)

    # Total row
    if rows:
        rows.append({
            "doctype":      "<b>TOTAL ({} dokumen)</b>".format(len(rows)),
            "name":         None,
            "posting_date": None,
            "cancelled_on": None,
            "cancelled_by": None,
            "warehouse":    None,
            "grand_total":  grand_total_sum,
            "remarks":      None,
        })

    return rows


def get_cancelled_docs(dt, from_date, to_date, wh_list):
    cfg = {
        "Sales Invoice": {
            "table": "tabSales Invoice",
            "warehouse_field": "set_warehouse",
            "amount_field": "grand_total",
            "remarks_field": "remarks",
        },
        "Purchase Invoice": {
            "table": "tabPurchase Invoice",
            "warehouse_field": "set_warehouse",
            "amount_field": "grand_total",
            "remarks_field": "remarks",
        },
        "Purchase Receipt": {
            "table": "tabPurchase Receipt",
            "warehouse_field": "set_warehouse",
            "amount_field": "total",
            "remarks_field": "remarks",
        },
        "Stock Entry": {
            "table": "tabStock Entry",
            "warehouse_field": "from_warehouse",
            "amount_field": "total_amount",
            "remarks_field": "remarks",
        },
        "Stock Reconciliation": {
            "table": "tabStock Reconciliation",
            "warehouse_field": "set_warehouse",
            "amount_field": "difference_amount",
            "remarks_field": "expense_account",
        },
    }

    c = cfg.get(dt)
    if not c:
        return []

    conditions = [
        "docstatus = 2",
        "DATE(modified) BETWEEN %(from_date)s AND %(to_date)s",
    ]
    values = {"from_date": from_date, "to_date": to_date}

    if wh_list:
        if len(wh_list) == 1:
            conditions.append("{} = %(warehouse)s".format(c["warehouse_field"]))
            values["warehouse"] = wh_list[0]
        else:
            wh_str = "({})".format(", ".join(["'{}'".format(w.replace("'","''")) for w in wh_list]))
            conditions.append("{} IN {}".format(c["warehouse_field"], wh_str))

    where = "WHERE " + " AND ".join(conditions)

    sql = """
        SELECT
            '{dt}' AS doctype,
            name,
            posting_date,
            modified AS cancelled_on,
            modified_by AS cancelled_by,
            {warehouse_field} AS warehouse,
            COALESCE({amount_field}, 0) AS grand_total,
            {remarks_field} AS remarks
        FROM `{table}`
        {where}
        ORDER BY modified DESC
    """.format(
        dt=dt,
        table=c["table"],
        warehouse_field=c["warehouse_field"],
        amount_field=c["amount_field"],
        remarks_field=c["remarks_field"],
        where=where,
    )

    return frappe.db.sql(sql, values, as_dict=True)
