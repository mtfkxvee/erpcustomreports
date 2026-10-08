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
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {"fieldname": "item_code",       "label": _("Kode Item"),          "fieldtype": "Link",     "options": "Item",     "width": 130},
        {"fieldname": "item_name",       "label": _("Nama Item"),          "fieldtype": "Data",     "width": 220},
        {"fieldname": "item_group",      "label": _("Item Group"),         "fieldtype": "Link",     "options": "Item Group","width": 130},
        {"fieldname": "warehouse",       "label": _("Warehouse"),          "fieldtype": "Link",     "options": "Warehouse", "width": 160},
        {"fieldname": "supplier",        "label": _("Supplier"),           "fieldtype": "Link",     "options": "Supplier",  "width": 180},
        {"fieldname": "sumber_supplier", "label": _("Sumber Supplier"),    "fieldtype": "Data",     "width": 130},
        {"fieldname": "opening_qty",     "label": _("Qty Awal"),           "fieldtype": "Float",    "width": 90},
        {"fieldname": "in_qty",          "label": _("Qty Masuk"),          "fieldtype": "Float",    "width": 90},
        {"fieldname": "out_qty",         "label": _("Qty Keluar"),         "fieldtype": "Float",    "width": 90},
        {"fieldname": "bal_qty",         "label": _("Qty Akhir"),          "fieldtype": "Float",    "width": 90},
        {"fieldname": "opening_val",     "label": _("Nilai Awal (Rp)"),    "fieldtype": "Currency", "width": 140},
        {"fieldname": "in_val",          "label": _("Nilai Masuk (Rp)"),   "fieldtype": "Currency", "width": 140},
        {"fieldname": "out_val",         "label": _("Nilai Keluar (Rp)"),  "fieldtype": "Currency", "width": 140},
        {"fieldname": "bal_val",         "label": _("Nilai Akhir (Rp)"),   "fieldtype": "Currency", "width": 150},
        {"fieldname": "valuation_rate",  "label": _("HPP / Unit (Rp)"),   "fieldtype": "Currency", "width": 140},
    ]


def get_data(filters):
    conditions = []
    values = {}

    if filters.get("from_date"):
        values["from_date"] = filters["from_date"]
    if filters.get("to_date"):
        values["to_date"] = filters["to_date"]
    if filters.get("item_code"):
        conditions.append("sle.item_code = %(item_code)s")
        values["item_code"] = filters["item_code"]
    if filters.get("item_group"):
        conditions.append("i.item_group = %(item_group)s")
        values["item_group"] = filters["item_group"]

    # Warehouse dengan support parent
    wh_condition = ""
    if filters.get("warehouse"):
        wh_list = get_warehouse_children(filters["warehouse"])
        if len(wh_list) == 1:
            conditions.append("sle.warehouse = %(warehouse)s")
            values["warehouse"] = wh_list[0]
        else:
            wh_str = "({})".format(", ".join(["'{}'".format(w.replace("'","''")) for w in wh_list]))
            conditions.append("sle.warehouse IN {}".format(wh_str))

    extra_where = (" AND " + " AND ".join(conditions)) if conditions else ""

    # Opening stock (sebelum from_date)
    opening_sql = (
        "SELECT sle.item_code, sle.warehouse,"
        " SUM(sle.actual_qty) AS opening_qty,"
        " SUM(sle.stock_value_difference) AS opening_val"
        " FROM `tabStock Ledger Entry` sle"
        " JOIN `tabItem` i ON i.name = sle.item_code"
        " WHERE sle.posting_date < %(from_date)s"
        " AND sle.is_cancelled = 0"
        + extra_where +
        " GROUP BY sle.item_code, sle.warehouse"
    )

    # In qty (masuk dalam periode)
    in_sql = (
        "SELECT sle.item_code, sle.warehouse,"
        " SUM(sle.actual_qty) AS in_qty,"
        " SUM(sle.stock_value_difference) AS in_val"
        " FROM `tabStock Ledger Entry` sle"
        " JOIN `tabItem` i ON i.name = sle.item_code"
        " WHERE sle.posting_date BETWEEN %(from_date)s AND %(to_date)s"
        " AND sle.actual_qty > 0"
        " AND sle.is_cancelled = 0"
        + extra_where +
        " GROUP BY sle.item_code, sle.warehouse"
    )

    # Out qty (keluar dalam periode)
    out_sql = (
        "SELECT sle.item_code, sle.warehouse,"
        " SUM(ABS(sle.actual_qty)) AS out_qty,"
        " SUM(ABS(sle.stock_value_difference)) AS out_val"
        " FROM `tabStock Ledger Entry` sle"
        " JOIN `tabItem` i ON i.name = sle.item_code"
        " WHERE sle.posting_date BETWEEN %(from_date)s AND %(to_date)s"
        " AND sle.actual_qty < 0"
        " AND sle.is_cancelled = 0"
        + extra_where +
        " GROUP BY sle.item_code, sle.warehouse"
    )

    # Valuation rate terbaru per item per warehouse
    val_sql = (
        "SELECT sle.item_code, sle.warehouse,"
        " sle.valuation_rate, i.item_name"
        " FROM `tabStock Ledger Entry` sle"
        " JOIN `tabItem` i ON i.name = sle.item_code"
        " WHERE sle.posting_date <= %(to_date)s"
        " AND sle.is_cancelled = 0"
        + extra_where +
        " ORDER BY sle.posting_date DESC, sle.posting_time DESC, sle.creation DESC"
    )

    opening_rows = frappe.db.sql(opening_sql, values, as_dict=True)
    in_rows      = frappe.db.sql(in_sql,      values, as_dict=True)
    out_rows     = frappe.db.sql(out_sql,     values, as_dict=True)
    val_rows     = frappe.db.sql(val_sql,     values, as_dict=True)

    # Build map per (item_code, warehouse)
    item_map = {}

    def get_key(r):
        return (r["item_code"], r["warehouse"])

    for r in opening_rows:
        k = get_key(r)
        item_map.setdefault(k, {})
        item_map[k]["opening_qty"] = flt(r["opening_qty"])
        item_map[k]["opening_val"] = flt(r["opening_val"])

    for r in in_rows:
        k = get_key(r)
        item_map.setdefault(k, {})
        item_map[k]["in_qty"] = flt(r["in_qty"])
        item_map[k]["in_val"] = flt(r["in_val"])

    for r in out_rows:
        k = get_key(r)
        item_map.setdefault(k, {})
        item_map[k]["out_qty"] = flt(r["out_qty"])
        item_map[k]["out_val"] = flt(r["out_val"])

    # Valuation rate & item_name — ambil yang pertama (sudah diurutkan terbaru)
    seen_val = set()
    for r in val_rows:
        k = get_key(r)
        if k not in seen_val:
            item_map.setdefault(k, {})
            item_map[k]["valuation_rate"] = flt(r["valuation_rate"])
            item_map[k]["item_name"] = r.get("item_name") or r["item_code"]
            seen_val.add(k)

    if not item_map:
        return []

    # Batch lookup item_group
    item_codes = list(set(k[0] for k in item_map.keys()))
    item_group_map = {}
    ig_rows = frappe.db.get_all("Item", filters={"name": ["in", item_codes]}, fields=["name", "item_group"])
    for ig in ig_rows:
        item_group_map[ig["name"]] = ig["item_group"]

    # Batch lookup supplier
    supplier_map = build_supplier_map(item_codes, filters.get("supplier"))

    rows = []
    total = {
        "opening_qty": 0, "in_qty": 0, "out_qty": 0, "bal_qty": 0,
        "opening_val": 0, "in_val": 0, "out_val": 0, "bal_val": 0,
    }

    for (item_code, warehouse), d in sorted(item_map.items()):
        sup_info = supplier_map.get(item_code, {})

        # Filter supplier
        if filters.get("supplier") and sup_info.get("supplier") != filters["supplier"]:
            continue
        if not sup_info.get("supplier"):
            continue

        opening_qty = flt(d.get("opening_qty", 0))
        in_qty      = flt(d.get("in_qty", 0))
        out_qty     = flt(d.get("out_qty", 0))
        bal_qty     = opening_qty + in_qty - out_qty

        opening_val = flt(d.get("opening_val", 0))
        in_val      = flt(d.get("in_val", 0))
        out_val     = flt(d.get("out_val", 0))
        bal_val     = opening_val + in_val - out_val

        val_rate    = flt(d.get("valuation_rate", 0))

        # Skip stok 0 kalau tidak dicentang
        if not filters.get("include_zero_stock") and bal_qty == 0:
            continue

        total["opening_qty"] += opening_qty
        total["in_qty"]      += in_qty
        total["out_qty"]     += out_qty
        total["bal_qty"]     += bal_qty
        total["opening_val"] += opening_val
        total["in_val"]      += in_val
        total["out_val"]     += out_val
        total["bal_val"]     += bal_val

        rows.append({
            "item_code":       item_code,
            "item_name":       d.get("item_name", item_code),
            "item_group":      item_group_map.get(item_code, ""),
            "warehouse":       warehouse,
            "supplier":        sup_info.get("supplier") or "-",
            "sumber_supplier": sup_info.get("sumber") or "-",
            "opening_qty":     opening_qty,
            "in_qty":          in_qty,
            "out_qty":         out_qty,
            "bal_qty":         bal_qty,
            "opening_val":     opening_val,
            "in_val":          in_val,
            "out_val":         out_val,
            "bal_val":         bal_val,
            "valuation_rate":  val_rate,
        })

    # Baris total
    if rows:
        rows.append({
            "item_code":       None,
            "item_name":       "<b>TOTAL ({} item)</b>".format(len(rows)),
            "item_group":      None,
            "warehouse":       None,
            "supplier":        None,
            "sumber_supplier": None,
            "opening_qty":     total["opening_qty"],
            "in_qty":          total["in_qty"],
            "out_qty":         total["out_qty"],
            "bal_qty":         total["bal_qty"],
            "opening_val":     total["opening_val"],
            "in_val":          total["in_val"],
            "out_val":         total["out_val"],
            "bal_val":         total["bal_val"],
            "valuation_rate":  None,
        })

    return rows


def build_supplier_map(item_codes, filter_supplier=None):
    if not item_codes:
        return {}
    result = {}
    fmt = ", ".join(["%s"] * len(item_codes))
    base_values = item_codes[:]
    sup_filter = ""
    sup_filter_po = ""
    if filter_supplier:
        sup_filter = "AND pi.supplier = %s"
        sup_filter_po = "AND po.supplier = %s"
        base_values = item_codes + [filter_supplier]

    pi_rows = frappe.db.sql(
        "SELECT pii.item_code, pi.supplier, pi.posting_date, pii.rate"
        " FROM `tabPurchase Invoice Item` pii"
        " JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent"
        " WHERE pii.item_code IN (" + fmt + ")"
        " AND pi.docstatus = 1 AND pi.is_return = 0"
        " " + sup_filter +
        " ORDER BY pi.posting_date DESC",
        base_values, as_dict=True
    )
    for row in pi_rows:
        ic = row["item_code"]
        if ic not in result:
            result[ic] = {"supplier": row["supplier"], "sumber": "Purchase Invoice",
                "last_purchase_date": row["posting_date"], "last_purchase_rate": flt(row.get("rate"))}

    missing = [ic for ic in item_codes if ic not in result]
    if missing:
        fmt2 = ", ".join(["%s"] * len(missing))
        base_values2 = missing + ([filter_supplier] if filter_supplier else [])
        po_rows = frappe.db.sql(
            "SELECT poi.item_code, po.supplier, po.transaction_date AS posting_date, poi.rate"
            " FROM `tabPurchase Order Item` poi"
            " JOIN `tabPurchase Order` po ON po.name = poi.parent"
            " WHERE poi.item_code IN (" + fmt2 + ")"
            " AND po.docstatus = 1"
            " " + sup_filter_po +
            " ORDER BY po.transaction_date DESC",
            base_values2, as_dict=True
        )
        for row in po_rows:
            ic = row["item_code"]
            if ic not in result:
                result[ic] = {"supplier": row["supplier"], "sumber": "Purchase Order",
                    "last_purchase_date": row["posting_date"], "last_purchase_rate": flt(row.get("rate"))}

    still_missing = [ic for ic in item_codes if ic not in result]
    if still_missing:
        fmt3 = ", ".join(["%s"] * len(still_missing))
        id_rows = frappe.db.sql(
            "SELECT parent AS item_code, default_supplier AS supplier"
            " FROM `tabItem Default`"
            " WHERE parent IN (" + fmt3 + ")"
            " AND default_supplier IS NOT NULL AND default_supplier != ''",
            still_missing, as_dict=True
        )
        for row in id_rows:
            ic = row["item_code"]
            if ic not in result:
                if not filter_supplier or row["supplier"] == filter_supplier:
                    result[ic] = {"supplier": row["supplier"], "sumber": "Item Default",
                        "last_purchase_date": None, "last_purchase_rate": 0}
    return result
