import frappe
from frappe import _


def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {
            "label": _("Warehouse"),
            "fieldname": "warehouse",
            "fieldtype": "Link",
            "options": "Warehouse",
            "width": 300,
        },
        {
            "label": _("Stock Balance (Rp)"),
            "fieldname": "stock_balance",
            "fieldtype": "Currency",
            "width": 200,
        },
    ]


def get_data(filters):
    company = filters.get("company")
    as_of_date = filters.get("as_of_date")

    if not company or not as_of_date:
        frappe.throw(_("Company and As of Date are required"))

    warehouses = frappe.db.sql(
        """
        SELECT
            w.name,
            w.warehouse_name,
            w.parent_warehouse,
            w.is_group,
            w.lft,
            w.rgt
        FROM `tabWarehouse` w
        WHERE w.company = %s
          AND w.disabled = 0
        ORDER BY w.lft
        """,
        (company,),
        as_dict=True,
    )

    if not warehouses:
        return []

    sle_data = frappe.db.sql(
        """
        SELECT
            sle.warehouse,
            SUM(sle.stock_value_difference) AS stock_balance
        FROM `tabStock Ledger Entry` sle
        INNER JOIN `tabWarehouse` w ON w.name = sle.warehouse
        WHERE sle.company = %s
          AND DATE(sle.posting_date) <= %s
          AND sle.is_cancelled = 0
        GROUP BY sle.warehouse
        """,
        (company, as_of_date),
        as_dict=True,
    )

    balance_map = {d.warehouse: d.stock_balance for d in sle_data}

    wh_map = {w.name: w for w in warehouses}

    computed = {w.name: balance_map.get(w.name, 0) for w in warehouses}

    for wh in warehouses:
        if wh.is_group:
            computed[wh.name] = sum(
                computed[leaf.name]
                for leaf in warehouses
                if leaf.lft >= wh.lft and leaf.rgt <= wh.rgt
            )

    data = []
    for wh in warehouses:
        indent = 0
        parent = wh.parent_warehouse
        while parent and parent in wh_map:
            indent += 1
            parent = wh_map[parent].parent_warehouse

        row = {
            "warehouse": wh.name,
            "stock_balance": computed.get(wh.name, 0),
            "indent": indent,
        }

        if wh.is_group:
            row["bold"] = 1

        data.append(row)

    return data
