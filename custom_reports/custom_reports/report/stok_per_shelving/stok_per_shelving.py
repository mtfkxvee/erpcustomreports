import frappe
from frappe.utils import flt


def execute(filters=None):
    filters = filters or {}
    return get_columns(), get_data(filters)


def get_columns():
    return [
        {"fieldname": "warehouse", "label": "Warehouse", "fieldtype": "Link",
         "options": "Warehouse", "width": 200},
        {"fieldname": "shelving", "label": "Shelving", "fieldtype": "Link",
         "options": "Shelving", "width": 180},
        {"fieldname": "item_code", "label": "Item Code", "fieldtype": "Link",
         "options": "Item", "width": 140},
        {"fieldname": "item_name", "label": "Item Name", "fieldtype": "Data", "width": 240},
        {"fieldname": "shelf_qty", "label": "Qty di Shelving", "fieldtype": "Float", "width": 120},
        {"fieldname": "warehouse_qty", "label": "Qty Warehouse", "fieldtype": "Float", "width": 120},
        {"fieldname": "unshelved_qty", "label": "Selisih vs Warehouse (harus 0)", "fieldtype": "Float",
         "width": 130},
    ]


def get_data(filters):
    conds, params = ["sb.actual_qty != 0"], []
    for key, col in (("warehouse", "sb.warehouse"), ("shelving", "sb.shelving"),
                     ("item_code", "sb.item_code")):
        if filters.get(key):
            conds.append(f"{col} = %s")
            params.append(filters[key])

    rows = frappe.db.sql(
        f"""select sb.warehouse, sb.shelving, sb.item_code, i.item_name, sb.actual_qty as shelf_qty
            from `tabShelving Bin` sb join `tabItem` i on i.name = sb.item_code
            where {' and '.join(conds)}
            order by sb.warehouse, sb.shelving, sb.item_code""",
        params, as_dict=True)

    wh_qty = {(b.warehouse, b.item_code): flt(b.actual_qty) for b in frappe.get_all(
        "Bin", fields=["warehouse", "item_code", "actual_qty"],
        filters={k: filters[k] for k in ("warehouse", "item_code") if filters.get(k)})}
    shelved = {}
    for b in frappe.db.sql(
            "select warehouse, item_code, sum(actual_qty) as qty from `tabShelving Bin` "
            "group by warehouse, item_code", as_dict=True):
        shelved[(b.warehouse, b.item_code)] = flt(b.qty)

    for r in rows:
        key = (r.warehouse, r.item_code)
        r.warehouse_qty = wh_qty.get(key, 0)
        r.unshelved_qty = r.warehouse_qty - shelved.get(key, 0)

    return rows
