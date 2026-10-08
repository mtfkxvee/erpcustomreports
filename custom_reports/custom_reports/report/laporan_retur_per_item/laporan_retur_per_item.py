import frappe
from frappe import _


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
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {"fieldname": "posting_date",  "label": _("Tanggal"),             "fieldtype": "Date",         "width": 100},
        {"fieldname": "return_type",   "label": _("Jenis Retur"),          "fieldtype": "Data",         "width": 120},
        {"fieldname": "voucher_no",    "label": _("No. Dokumen"),          "fieldtype": "Dynamic Link", "options": "voucher_type", "width": 160},
        {"fieldname": "item_code",     "label": _("Kode Item"),            "fieldtype": "Link",         "options": "Item",         "width": 120},
        {"fieldname": "item_name",     "label": _("Nama Item"),            "fieldtype": "Data",         "width": 200},
        {"fieldname": "warehouse",     "label": _("Source Warehouse"),     "fieldtype": "Link",         "options": "Warehouse",    "width": 160},
        {"fieldname": "qty_retur",     "label": _("Qty Retur"),            "fieldtype": "Float",        "width": 90},
        {"fieldname": "uom",           "label": _("Satuan"),               "fieldtype": "Data",         "width": 70},
        {"fieldname": "hpp_per_unit",  "label": _("HPP / Unit (Rp)"),     "fieldtype": "Currency",     "width": 140},
        {"fieldname": "hj_per_unit",   "label": _("HJ / Unit (Rp)"),      "fieldtype": "Currency",     "width": 140},
        {"fieldname": "total_hpp",     "label": _("Total HPP (Rp)"),      "fieldtype": "Currency",     "width": 150},
        {"fieldname": "total_hj",      "label": _("Total HJ (Rp)"),       "fieldtype": "Currency",     "width": 150},
        {"fieldname": "selisih",       "label": _("Selisih HJ-HPP (Rp)"), "fieldtype": "Currency",     "width": 160},
        {"fieldname": "party",         "label": _("Customer / Supplier"),  "fieldtype": "Data",         "width": 160},
    ]


def get_data(filters):
    rows = []
    return_type = filters.get("return_type")
    if not return_type or return_type == "Sales Return":
        rows += get_sales_returns(filters)
    if not return_type or return_type == "Purchase Return":
        rows += get_purchase_returns(filters)
    rows.sort(key=lambda x: x.get("posting_date") or "", reverse=True)
    return rows


def build_outlet_condition(filters, alias="si"):
    outlet_list = get_outlet_list(filters)
    if not outlet_list:
        return "", {}
    if len(outlet_list) == 1:
        return "AND {}.custom_outlet = %(outlet_single)s".format(alias), {"outlet_single": outlet_list[0]}
    out_str = "({})".format(", ".join(["'{}'".format(o.replace("'","''")) for o in outlet_list]))
    return "AND {}.custom_outlet IN {}".format(alias, out_str), {}


def get_sales_returns(filters):
    conditions = ["si.docstatus = 1", "si.is_return = 1"]
    values = {}

    if filters.get("from_date"):
        conditions.append("si.posting_date >= %(from_date)s")
        values["from_date"] = filters["from_date"]
    if filters.get("to_date"):
        conditions.append("si.posting_date <= %(to_date)s")
        values["to_date"] = filters["to_date"]
    if filters.get("warehouse"):
        conditions.append("sii.warehouse = %(warehouse)s")
        values["warehouse"] = filters["warehouse"]
    if filters.get("item_code"):
        conditions.append("sii.item_code = %(item_code)s")
        values["item_code"] = filters["item_code"]
    if filters.get("customer"):
        conditions.append("si.customer = %(customer)s")
        values["customer"] = filters["customer"]

    # Outlet filter
    outlet_cond, outlet_vals = build_outlet_condition(filters, "si")
    if outlet_cond:
        conditions.append(outlet_cond.lstrip("AND "))
        values.update(outlet_vals)

    where = "WHERE " + " AND ".join(conditions)

    sql = (
        "SELECT si.posting_date, 'Sales Return' AS return_type,"
        " si.name AS voucher_no, 'Sales Invoice' AS voucher_type,"
        " sii.item_code, sii.item_name, sii.warehouse,"
        " ABS(sii.qty) AS qty_retur, sii.uom, sii.rate AS hj_per_unit,"
        " COALESCE(("
        "  SELECT sle.valuation_rate FROM `tabStock Ledger Entry` sle"
        "  WHERE sle.voucher_type = 'Sales Invoice' AND sle.voucher_no = si.name"
        "  AND sle.item_code = sii.item_code AND sle.warehouse = sii.warehouse"
        "  LIMIT 1"
        " ), 0) AS hpp_per_unit,"
        " si.customer AS party"
        " FROM `tabSales Invoice Item` sii"
        " JOIN `tabSales Invoice` si ON si.name = sii.parent"
        " {where}"
        " ORDER BY si.posting_date DESC"
    ).format(where=where)

    rows = frappe.db.sql(sql, values, as_dict=True)
    for r in rows:
        r["total_hpp"] = r["qty_retur"] * r["hpp_per_unit"]
        r["total_hj"]  = r["qty_retur"] * r["hj_per_unit"]
        r["selisih"]   = r["total_hj"] - r["total_hpp"]
    return rows


def get_purchase_returns(filters):
    conditions = ["pi.docstatus = 1", "pi.is_return = 1"]
    values = {}

    if filters.get("from_date"):
        conditions.append("pi.posting_date >= %(from_date)s")
        values["from_date"] = filters["from_date"]
    if filters.get("to_date"):
        conditions.append("pi.posting_date <= %(to_date)s")
        values["to_date"] = filters["to_date"]
    if filters.get("warehouse"):
        conditions.append("pii.warehouse = %(warehouse)s")
        values["warehouse"] = filters["warehouse"]
    if filters.get("item_code"):
        conditions.append("pii.item_code = %(item_code)s")
        values["item_code"] = filters["item_code"]
    if filters.get("supplier"):
        conditions.append("pi.supplier = %(supplier)s")
        values["supplier"] = filters["supplier"]

    where = "WHERE " + " AND ".join(conditions)

    sql = (
        "SELECT pi.posting_date, 'Purchase Return' AS return_type,"
        " pi.name AS voucher_no, 'Purchase Invoice' AS voucher_type,"
        " pii.item_code, pii.item_name, pii.warehouse,"
        " ABS(pii.qty) AS qty_retur, pii.uom, pii.rate AS hj_per_unit,"
        " COALESCE(("
        "  SELECT sle.valuation_rate FROM `tabStock Ledger Entry` sle"
        "  WHERE sle.voucher_type = 'Purchase Invoice' AND sle.voucher_no = pi.name"
        "  AND sle.item_code = pii.item_code AND sle.warehouse = pii.warehouse"
        "  LIMIT 1"
        " ), 0) AS hpp_per_unit,"
        " pi.supplier AS party"
        " FROM `tabPurchase Invoice Item` pii"
        " JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent"
        " {where}"
        " ORDER BY pi.posting_date DESC"
    ).format(where=where)

    rows = frappe.db.sql(sql, values, as_dict=True)
    for r in rows:
        r["total_hpp"] = r["qty_retur"] * r["hpp_per_unit"]
        r["total_hj"]  = r["qty_retur"] * r["hj_per_unit"]
        r["selisih"]   = r["total_hj"] - r["total_hpp"]
    return rows
