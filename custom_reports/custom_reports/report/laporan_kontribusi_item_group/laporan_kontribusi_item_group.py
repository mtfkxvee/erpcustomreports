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
        frappe.msgprint(
            "Silakan pilih <b>Dari Tanggal</b> dan <b>Sampai Tanggal</b> terlebih dahulu.",
            indicator="orange", alert=True
        )
        return [], []
    columns = get_columns()
    data, chart, summary = get_data(filters)
    return columns, data, None, chart, summary


def get_columns():
    return [
        {"fieldname": "item_group",   "label": _("Item Group"),   "fieldtype": "Link", "options": "Item Group", "width": 160},
        {"fieldname": "department",   "label": _("Department"),   "fieldtype": "Data",                          "width": 130},
        {"fieldname": "category",     "label": _("Category"),     "fieldtype": "Data",                          "width": 130},
        {"fieldname": "sub_category", "label": _("Sub Category"), "fieldtype": "Data",                          "width": 130},
        {"fieldname": "qty",          "label": _("Qty Terjual"),  "fieldtype": "Float",                         "width": 110},
        {"fieldname": "sales",        "label": _("Sales (Rp)"),   "fieldtype": "Currency",                      "width": 160},
        {"fieldname": "kontribusi",   "label": _("Kontribusi (%)"), "fieldtype": "Percent",                     "width": 130},
    ]


def get_data(filters):
    conditions = ["si.docstatus = 1", "si.is_return = 0"]
    values = {}

    conditions.append("si.posting_date BETWEEN %(from_date)s AND %(to_date)s")
    values["from_date"] = filters["from_date"]
    values["to_date"]   = filters["to_date"]

    # Warehouse dengan support parent
    if filters.get("warehouse"):
        wh_list = get_warehouse_children(filters["warehouse"])
        if len(wh_list) == 1:
            conditions.append("sii.warehouse = %(warehouse)s")
            values["warehouse"] = wh_list[0]
        else:
            wh_str = "({})".format(", ".join(["'{}'".format(w.replace("'","''")) for w in wh_list]))
            conditions.append("sii.warehouse IN {}".format(wh_str))

    if filters.get("item_group"):
        conditions.append("i.item_group = %(item_group)s")
        values["item_group"] = filters["item_group"]

    if filters.get("department"):
        conditions.append("i.department = %(department)s")
        values["department"] = filters["department"]

    if filters.get("category"):
        conditions.append("i.category = %(category)s")
        values["category"] = filters["category"]

    if filters.get("sub_category"):
        conditions.append("i.sub_category = %(sub_category)s")
        values["sub_category"] = filters["sub_category"]

    where = "WHERE " + " AND ".join(conditions)

    sql = (
        "SELECT"
        " i.item_group,"
        " i.department,"
        " i.category,"
        " i.sub_category,"
        " SUM(sii.qty) AS qty,"
        " SUM(sii.base_net_amount) AS sales"
        " FROM `tabSales Invoice Item` sii"
        " JOIN `tabSales Invoice` si ON si.name = sii.parent"
        " JOIN `tabItem` i ON i.name = sii.item_code"
        " {where}"
        " GROUP BY i.item_group, i.department, i.category, i.sub_category"
        " ORDER BY sales DESC"
    ).format(where=where)

    raw = frappe.db.sql(sql, values, as_dict=True)

    if not raw:
        return [], None, None

    grand_total = sum(flt(r["sales"]) for r in raw)

    rows = []
    for r in raw:
        sales = flt(r["sales"])
        qty   = flt(r["qty"])
        kontribusi = (sales / grand_total * 100) if grand_total > 0 else 0
        rows.append({
            "item_group":   r["item_group"] or "-",
            "department":   r["department"] or "-",
            "category":     r["category"] or "-",
            "sub_category": r["sub_category"] or "-",
            "qty":          qty,
            "sales":        sales,
            "kontribusi":   kontribusi,
        })

    # Baris total
    grand_qty = sum(r["qty"] for r in rows)
    rows.append({
        "item_group":   "<b>TOTAL ({} group)</b>".format(len(rows)),
        "department":   None,
        "category":     None,
        "sub_category": None,
        "qty":          grand_qty,
        "sales":        grand_total,
        "kontribusi":   100.0,
    })

    # Chart — top 10
    chart_data = rows[:-1][:10]
    chart = {
        "data": {
            "labels": [r["item_group"] for r in chart_data],
            "datasets": [
                {"name": "Sales (Rp)",     "values": [r["sales"] for r in chart_data],      "chartType": "bar"},
                {"name": "Kontribusi (%)", "values": [r["kontribusi"] for r in chart_data], "chartType": "line"},
            ]
        },
        "type": "axis-mixed",
        "fieldtype": "Currency",
        "colors": ["#5E64FF", "#FF9800"],
        "axisOptions": {"xIsSeries": 1},
        "height": 300,
    }

    # Summary
    top1 = rows[0] if rows else {}
    summary = [
        {"value": grand_total,                  "label": "Total Sales",        "datatype": "Currency", "indicator": "green"},
        {"value": grand_qty,                    "label": "Total Qty",          "datatype": "Float",    "indicator": "blue"},
        {"value": len(rows) - 1,                "label": "Jumlah Item Group",  "datatype": "Int",      "indicator": "orange"},
        {"value": top1.get("kontribusi", 0),    "label": "Kontribusi Terbesar","datatype": "Percent",  "indicator": "red"},
    ]

    return rows, chart, summary
