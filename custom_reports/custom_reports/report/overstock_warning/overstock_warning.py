import frappe
from frappe.utils import flt, nowdate


def execute(filters=None):
    filters = filters or {}

    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {
            "fieldname": "item_code",
            "label": "Item Code",
            "fieldtype": "Link",
            "options": "Item",
            "width": 150,
        },
        {
            "fieldname": "item_name",
            "label": "Item Name",
            "fieldtype": "Data",
            "width": 220,
        },
        {
            "fieldname": "warehouse",
            "label": "Warehouse",
            "fieldtype": "Link",
            "options": "Warehouse",
            "width": 200,
        },
        {
            "fieldname": "uom",
            "label": "UOM",
            "fieldtype": "Data",
            "width": 70,
        },
        {
            "fieldname": "min_qty",
            "label": "Min Qty",
            "fieldtype": "Float",
            "width": 100,
        },
        {
            "fieldname": "max_qty",
            "label": "Max Qty",
            "fieldtype": "Float",
            "width": 100,
        },
        {
            "fieldname": "actual_qty",
            "label": "Actual Qty",
            "fieldtype": "Float",
            "width": 110,
        },
        {
            "fieldname": "selisih",
            "label": "Selisih (Actual - Max)",
            "fieldtype": "Float",
            "width": 160,
        },
        {
            "fieldname": "owner",
            "label": "Owner",
            "fieldtype": "Data",
            "width": 180,
        },
        {
            "fieldname": "valid_from",
            "label": "Valid From",
            "fieldtype": "Date",
            "width": 110,
        },
        {
            "fieldname": "min_max_name",
            "label": "Min Max Record",
            "fieldtype": "Link",
            "options": "Item Min Max",
            "width": 200,
        },
    ]


def get_data(filters):
    conditions = "m.is_active = 1"
    values = {}

    if filters.get("warehouse"):
        conditions += " AND m.warehouse = %(warehouse)s"
        values["warehouse"] = filters["warehouse"]

    if filters.get("item_code"):
        conditions += " AND m.item_code = %(item_code)s"
        values["item_code"] = filters["item_code"]

    rows = frappe.db.sql(
        """
        SELECT
            m.name         AS min_max_name,
            m.item_code,
            m.item_name,
            m.warehouse,
            m.uom,
            m.min_qty,
            m.max_qty,
            m.owner,
            m.valid_from,
            COALESCE(b.actual_qty, 0) AS actual_qty
        FROM `tabItem Min Max` m
        LEFT JOIN `tabBin` b
            ON b.item_code = m.item_code
            AND b.warehouse = m.warehouse
        WHERE {conditions}
          AND COALESCE(b.actual_qty, 0) > m.max_qty
        ORDER BY (COALESCE(b.actual_qty, 0) - m.max_qty) DESC
        """.format(conditions=conditions),
        values,
        as_dict=True,
    )

    data = []
    for r in rows:
        r["selisih"] = flt(r["actual_qty"]) - flt(r["max_qty"])
        data.append(r)

    return data
