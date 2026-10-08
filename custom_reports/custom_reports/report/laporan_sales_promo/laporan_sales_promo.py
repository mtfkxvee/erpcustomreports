import frappe
import json
from frappe import _


def get_warehouse_children(warehouse):
    wh = frappe.db.get_value("Warehouse", warehouse, ["lft", "rgt", "is_group"], as_dict=True)
    if not wh:
        return [warehouse]
    if not wh.is_group:
        return [warehouse]
    children = frappe.db.sql(
        "SELECT name FROM `tabWarehouse`"
        " WHERE lft >= %s AND rgt <= %s AND is_group = 0",
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
    data, total_row = get_data(filters)
    if total_row:
        data.append(total_row)
    return columns, data


def get_columns():
    return [
        {"fieldname": "posting_date",   "label": "Tanggal",           "fieldtype": "Date",     "width": 100},
        {"fieldname": "invoice_no",     "label": "No. Invoice",       "fieldtype": "Link",     "options": "Sales Invoice", "width": 170},
        {"fieldname": "customer",       "label": "Customer",          "fieldtype": "Link",     "options": "Customer",      "width": 160},
        {"fieldname": "item_code",      "label": "Kode Item",         "fieldtype": "Link",     "options": "Item",          "width": 120},
        {"fieldname": "item_name",      "label": "Nama Item",         "fieldtype": "Data",     "width": 200},
        {"fieldname": "warehouse",      "label": "Warehouse",         "fieldtype": "Link",     "options": "Warehouse",     "width": 150},
        {"fieldname": "qty",            "label": "Qty",               "fieldtype": "Float",    "width": 70},
        {"fieldname": "uom",            "label": "Satuan",            "fieldtype": "Data",     "width": 70},
        {"fieldname": "harga_normal",   "label": "Harga Normal (Rp)", "fieldtype": "Currency", "width": 150},
        {"fieldname": "harga_diskon",   "label": "Harga Diskon (Rp)", "fieldtype": "Currency", "width": 150},
        {"fieldname": "diskon_persen",  "label": "Diskon (%)",        "fieldtype": "Percent",  "width": 100},
        {"fieldname": "diskon_nominal", "label": "Diskon/Unit (Rp)",  "fieldtype": "Currency", "width": 140},
        {"fieldname": "total_diskon",   "label": "Total Diskon (Rp)", "fieldtype": "Currency", "width": 150},
        {"fieldname": "tipe_diskon",    "label": "Tipe Diskon",       "fieldtype": "Data",     "width": 120},
        {"fieldname": "pricing_rules",  "label": "Pricing Rule",      "fieldtype": "Data",     "width": 200},
    ]


def get_data(filters):
    conditions = [
        "si.docstatus = 1",
        "si.is_return = 0",
        "(sii.pricing_rules IS NOT NULL AND sii.pricing_rules != '' AND sii.pricing_rules != '[]')",
    ]
    values = {}

    if filters.get("from_date"):
        conditions.append("si.posting_date >= %(from_date)s")
        values["from_date"] = filters["from_date"]
    if filters.get("to_date"):
        conditions.append("si.posting_date <= %(to_date)s")
        values["to_date"] = filters["to_date"]
    if filters.get("customer"):
        conditions.append("si.customer = %(customer)s")
        values["customer"] = filters["customer"]
    if filters.get("item_code"):
        conditions.append("sii.item_code = %(item_code)s")
        values["item_code"] = filters["item_code"]
    if filters.get("pricing_rule"):
        conditions.append("sii.pricing_rules LIKE %(pricing_rule_like)s")
        values["pricing_rule_like"] = "%" + filters["pricing_rule"] + "%"

    # Warehouse dengan support parent
    if filters.get("warehouse"):
        wh_list = get_warehouse_children(filters["warehouse"])
        if len(wh_list) == 1:
            conditions.append("sii.warehouse = %(warehouse)s")
            values["warehouse"] = wh_list[0]
        else:
            wh_str = "({})".format(", ".join(["'{}'".format(w.replace("'","''")) for w in wh_list]))
            conditions.append("sii.warehouse IN {}".format(wh_str))

    where = "WHERE " + " AND ".join(conditions)

    sql = (
        "SELECT si.posting_date, si.name AS invoice_no, si.customer,"
        " sii.item_code, sii.item_name, sii.warehouse, sii.qty, sii.uom,"
        " sii.price_list_rate AS harga_normal, sii.rate AS harga_diskon,"
        " sii.discount_percentage AS diskon_persen, sii.discount_amount AS diskon_amount,"
        " sii.distributed_discount_amount AS dist_diskon,"
        " sii.is_free_item, sii.pricing_rules"
        " FROM `tabSales Invoice Item` sii"
        " JOIN `tabSales Invoice` si ON si.name = sii.parent"
        " {where}"
        " ORDER BY si.posting_date DESC, si.name, sii.item_code"
    ).format(where=where)

    raw = frappe.db.sql(sql, values, as_dict=True)

    rows = []
    total_qty = 0
    total_diskon_sum = 0

    for r in raw:
        harga_normal  = float(r.get("harga_normal") or 0)
        harga_diskon  = float(r.get("harga_diskon") or 0)
        qty           = float(r.get("qty") or 0)
        diskon_persen = float(r.get("diskon_persen") or 0)
        diskon_amount = float(r.get("diskon_amount") or 0)
        dist_diskon   = float(r.get("dist_diskon") or 0)
        is_free       = r.get("is_free_item")

        if is_free:
            diskon_per_unit = harga_normal
            tipe_diskon = "Free Item"
        elif diskon_persen > 0:
            diskon_per_unit = harga_normal * diskon_persen / 100
            tipe_diskon = "Diskon %"
        elif diskon_amount > 0:
            diskon_per_unit = diskon_amount
            tipe_diskon = "Diskon Nominal"
        elif dist_diskon > 0:
            diskon_per_unit = dist_diskon
            tipe_diskon = "Diskon Nominal"
        elif harga_normal > 0 and harga_diskon < harga_normal:
            diskon_per_unit = harga_normal - harga_diskon
            tipe_diskon = "Fixed Price"
        else:
            diskon_per_unit = 0
            tipe_diskon = "-"

        total_item_diskon = diskon_per_unit * qty

        pr_raw = r.get("pricing_rules") or ""
        try:
            pr_list = json.loads(pr_raw) if pr_raw else []
            pr_str = ", ".join(pr_list) if isinstance(pr_list, list) else pr_raw
        except Exception:
            pr_str = pr_raw

        total_qty += qty
        total_diskon_sum += total_item_diskon

        rows.append({
            "posting_date":   r["posting_date"],
            "invoice_no":     r["invoice_no"],
            "customer":       r["customer"],
            "item_code":      r["item_code"],
            "item_name":      r["item_name"],
            "warehouse":      r["warehouse"],
            "qty":            qty,
            "uom":            r.get("uom"),
            "harga_normal":   harga_normal,
            "harga_diskon":   harga_diskon,
            "diskon_persen":  diskon_persen,
            "diskon_nominal": diskon_per_unit,
            "total_diskon":   total_item_diskon,
            "tipe_diskon":    tipe_diskon,
            "pricing_rules":  pr_str,
        })

    return rows, None
