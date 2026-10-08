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


def build_wh_condition(warehouse, field):
    if not warehouse:
        return "", {}
    wh_list = get_warehouse_children(warehouse)
    if len(wh_list) == 1:
        key = field.replace(".", "_")
        return "AND {} = %({})s".format(field, key), {key: wh_list[0]}
    wh_str = "({})".format(", ".join(["'{}'".format(w.replace("'","''")) for w in wh_list]))
    return "AND {} IN {}".format(field, wh_str), {}


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
    return columns, data


def get_columns():
    return [
        {"fieldname": "posting_date",    "label": _("Tanggal"),           "fieldtype": "Date",         "width": 100},
        {"fieldname": "posting_time",    "label": _("Waktu"),             "fieldtype": "Time",         "width": 80},
        {"fieldname": "item_code",       "label": _("Item"),              "fieldtype": "Link",         "options": "Item",      "width": 130},
        {"fieldname": "item_name",       "label": _("Nama Item"),         "fieldtype": "Data",         "width": 200},
        {"fieldname": "item_group",      "label": _("Item Group"),        "fieldtype": "Link",         "options": "Item Group","width": 120},
        {"fieldname": "brand",           "label": _("Brand"),             "fieldtype": "Link",         "options": "Brand",     "width": 100},
        {"fieldname": "qty_in",          "label": _("Qty In"),            "fieldtype": "Float",        "width": 80},
        {"fieldname": "qty_out",         "label": _("Qty Out"),           "fieldtype": "Float",        "width": 80},
        {"fieldname": "balance_qty",     "label": _("Balance"),           "fieldtype": "Float",        "width": 90},
        {"fieldname": "warehouse",       "label": _("Warehouse Asal"),    "fieldtype": "Link",         "options": "Warehouse", "width": 160},
        {"fieldname": "target_warehouse","label": _("Target Warehouse"),  "fieldtype": "Link",         "options": "Warehouse", "width": 160},
        {"fieldname": "voucher_no",      "label": _("No. Voucher"),       "fieldtype": "Dynamic Link", "options": "voucher_type", "width": 170},
        {"fieldname": "incoming_rate",   "label": _("Incoming Rate (Rp)"), "fieldtype": "Currency",   "width": 140},
        {"fieldname": "avg_rate",        "label": _("Avg Rate (Rp)"),    "fieldtype": "Currency",     "width": 130},
        {"fieldname": "valuation_rate",  "label": _("Valuation Rate (Rp)"), "fieldtype": "Currency",  "width": 150},
        {"fieldname": "balance_value",   "label": _("Balance Value (Rp)"), "fieldtype": "Currency",   "width": 150},
        {"fieldname": "value_change",    "label": _("Value Change (Rp)"), "fieldtype": "Currency",    "width": 140},
    ]


def get_data(filters):
    conditions = [
        "sle.voucher_type = 'Stock Entry'",
        "sle.is_cancelled = 0",
        "sle.posting_date BETWEEN %(from_date)s AND %(to_date)s",
        "se.stock_entry_type = 'Material Transfer'",
    ]
    values = {
        "from_date": filters["from_date"],
        "to_date":   filters["to_date"],
    }

    # Warehouse asal
    wh_cond, wh_vals = build_wh_condition(filters.get("warehouse"), "sle.warehouse")
    if wh_cond:
        conditions.append(wh_cond.lstrip("AND "))
        values.update(wh_vals)

    # Target warehouse
    twh_cond, twh_vals = build_wh_condition(filters.get("target_warehouse"), "sei.t_warehouse")
    if twh_cond:
        conditions.append(twh_cond.lstrip("AND "))
        values.update(twh_vals)

    if filters.get("item_code"):
        conditions.append("sle.item_code = %(item_code)s")
        values["item_code"] = filters["item_code"]

    if filters.get("item_group"):
        conditions.append("i.item_group = %(item_group)s")
        values["item_group"] = filters["item_group"]

    if filters.get("brand"):
        conditions.append("i.brand = %(brand)s")
        values["brand"] = filters["brand"]

    where = "WHERE " + " AND ".join(conditions)

    sql = (
        "SELECT"
        " sle.posting_date,"
        " sle.posting_time,"
        " sle.item_code,"
        " i.item_name,"
        " i.item_group,"
        " i.brand,"
        " CASE WHEN sle.actual_qty > 0 THEN sle.actual_qty ELSE 0 END AS qty_in,"
        " CASE WHEN sle.actual_qty < 0 THEN ABS(sle.actual_qty) ELSE 0 END AS qty_out,"
        " sle.qty_after_transaction AS balance_qty,"
        " sle.warehouse,"
        " sei.t_warehouse AS target_warehouse,"
        " sle.voucher_no,"
        " 'Stock Entry' AS voucher_type,"
        " sle.incoming_rate,"
        " CASE WHEN sle.actual_qty != 0"
        "   THEN ABS(sle.stock_value_difference / sle.actual_qty)"
        "   ELSE 0 END AS avg_rate,"
        " sle.valuation_rate,"
        " sle.stock_value AS balance_value,"
        " sle.stock_value_difference AS value_change"
        " FROM `tabStock Ledger Entry` sle"
        " JOIN `tabStock Entry` se ON se.name = sle.voucher_no"
        " JOIN `tabItem` i ON i.name = sle.item_code"
        " LEFT JOIN `tabStock Entry Detail` sei"
        "   ON sei.parent = sle.voucher_no AND sei.item_code = sle.item_code"
        "   AND sei.s_warehouse = sle.warehouse"
        " {where}"
        " ORDER BY sle.posting_date ASC, sle.posting_time ASC, sle.voucher_no, sle.item_code"
    ).format(where=where)

    rows = frappe.db.sql(sql, values, as_dict=True)

    result = []
    for r in rows:
        result.append({
            "posting_date":    r["posting_date"],
            "posting_time":    str(r["posting_time"]),
            "item_code":       r["item_code"],
            "item_name":       r["item_name"],
            "item_group":      r["item_group"],
            "brand":           r["brand"],
            "qty_in":          flt(r["qty_in"]),
            "qty_out":         flt(r["qty_out"]),
            "balance_qty":     flt(r["balance_qty"]),
            "warehouse":       r["warehouse"],
            "target_warehouse":r["target_warehouse"],
            "voucher_no":      r["voucher_no"],
            "voucher_type":    r["voucher_type"],
            "incoming_rate":   flt(r["incoming_rate"]),
            "avg_rate":        flt(r["avg_rate"]),
            "valuation_rate":  flt(r["valuation_rate"]),
            "balance_value":   flt(r["balance_value"]),
            "value_change":    flt(r["value_change"]),
        })

    return result
