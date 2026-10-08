import frappe
from frappe import _


def execute(filters=None):
    if not filters:
        filters = {}

    if not filters.get("from_date") or not filters.get("to_date"):
        frappe.msgprint(
            "Silakan pilih <b>Dari Tanggal</b> dan <b>Sampai Tanggal</b> terlebih dahulu.",
            indicator="orange", alert=True
        )
        return [], []

    warehouses = get_active_warehouses(filters)
    columns = get_columns(warehouses)
    data = get_data(filters, warehouses)
    return columns, data


def get_active_warehouses(filters):
    conditions = ["si.docstatus = 1", "si.is_return = 0"]
    values = {}
    if filters.get("from_date"):
        conditions.append("si.posting_date >= %(from_date)s")
        values["from_date"] = filters["from_date"]
    if filters.get("to_date"):
        conditions.append("si.posting_date <= %(to_date)s")
        values["to_date"] = filters["to_date"]
    where = "WHERE " + " AND ".join(conditions)
    rows = frappe.db.sql(
        "SELECT DISTINCT sii.warehouse"
        " FROM `tabSales Invoice Item` sii"
        " JOIN `tabSales Invoice` si ON si.name = sii.parent"
        " {where}"
        " AND sii.warehouse IS NOT NULL AND sii.warehouse != ''"
        " ORDER BY sii.warehouse".format(where=where),
        values, as_dict=True
    )
    return [r["warehouse"] for r in rows]


def get_columns(warehouses):
    cols = [
        {"fieldname": "item_code",          "label": "Kode Item",                "fieldtype": "Link",     "options": "Item",     "width": 130},
        {"fieldname": "item_name",          "label": "Nama Item",                "fieldtype": "Data",     "width": 220},
        {"fieldname": "supplier",           "label": "Supplier",                 "fieldtype": "Link",     "options": "Supplier", "width": 180},
        {"fieldname": "sumber_supplier",    "label": "Sumber",                   "fieldtype": "Data",     "width": 120},
        {"fieldname": "last_purchase_date", "label": "Tgl Beli Terakhir",        "fieldtype": "Date",     "width": 130},
        {"fieldname": "last_purchase_rate", "label": "Harga Beli Terakhir (Rp)", "fieldtype": "Currency", "width": 160},
        {"fieldname": "total_qty",          "label": "Total Qty",                "fieldtype": "Float",    "width": 90},
        {"fieldname": "total_penjualan",    "label": "Total Penjualan (Rp)",     "fieldtype": "Currency", "width": 160},
    ]
    for wh in warehouses:
        wh_key = wh.replace(" ", "_").replace("-", "_").replace(".", "_").lower()
        cols.append({"fieldname": "qty_" + wh_key, "label": "Qty | " + wh, "fieldtype": "Float",    "width": 100})
        cols.append({"fieldname": "amt_" + wh_key, "label": "Rp | "  + wh, "fieldtype": "Currency", "width": 130})
    return cols


def get_data(filters, warehouses):
    conditions = ["si.docstatus = 1", "si.is_return = 0"]
    values = {}
    if filters.get("from_date"):
        conditions.append("si.posting_date >= %(from_date)s")
        values["from_date"] = filters["from_date"]
    if filters.get("to_date"):
        conditions.append("si.posting_date <= %(to_date)s")
        values["to_date"] = filters["to_date"]
    if filters.get("item_code"):
        conditions.append("sii.item_code = %(item_code)s")
        values["item_code"] = filters["item_code"]
    if filters.get("customer"):
        conditions.append("si.customer = %(customer)s")
        values["customer"] = filters["customer"]
    where = "WHERE " + " AND ".join(conditions)
    sql = (
        "SELECT sii.item_code, sii.item_name, sii.warehouse,"
        " SUM(sii.qty) AS qty, SUM(sii.qty * sii.rate) AS amount"
        " FROM `tabSales Invoice Item` sii"
        " JOIN `tabSales Invoice` si ON si.name = sii.parent"
        " {where}"
        " GROUP BY sii.item_code, sii.item_name, sii.warehouse"
        " ORDER BY sii.item_code"
    ).format(where=where)
    raw = frappe.db.sql(sql, values, as_dict=True)
    if not raw:
        return []
    item_map = {}
    for r in raw:
        ic = r["item_code"]
        if ic not in item_map:
            item_map[ic] = {"item_code": ic, "item_name": r["item_name"], "total_qty": 0, "total_penjualan": 0}
        item_map[ic]["total_qty"] += float(r["qty"] or 0)
        item_map[ic]["total_penjualan"] += float(r["amount"] or 0)
        wh_key = r["warehouse"].replace(" ", "_").replace("-", "_").replace(".", "_").lower()
        item_map[ic]["qty_" + wh_key] = float(r["qty"] or 0)
        item_map[ic]["amt_" + wh_key] = float(r["amount"] or 0)
    item_codes = list(item_map.keys())
    supplier_map = build_supplier_map(item_codes, filters.get("supplier"))
    rows = []
    grand_qty = 0
    grand_amt = 0
    for ic, item in item_map.items():
        sup_info = supplier_map.get(ic, {})
        if filters.get("supplier") and sup_info.get("supplier") != filters["supplier"]:
            continue
        if not sup_info.get("supplier"):
            continue
        row = {
            "item_code":          ic,
            "item_name":          item["item_name"],
            "supplier":           sup_info.get("supplier"),
            "sumber_supplier":    sup_info.get("sumber") or "-",
            "last_purchase_date": sup_info.get("last_purchase_date"),
            "last_purchase_rate": float(sup_info.get("last_purchase_rate") or 0),
            "total_qty":          item["total_qty"],
            "total_penjualan":    item["total_penjualan"],
        }
        for wh in warehouses:
            wh_key = wh.replace(" ", "_").replace("-", "_").replace(".", "_").lower()
            row["qty_" + wh_key] = item.get("qty_" + wh_key, 0)
            row["amt_" + wh_key] = item.get("amt_" + wh_key, 0)
        grand_qty += item["total_qty"]
        grand_amt += item["total_penjualan"]
        rows.append(row)
    rows.sort(key=lambda x: x["item_code"])
    if rows:
        total_row = {
            "item_code": None,
            "item_name": "<b>TOTAL (" + str(len(rows)) + " item)</b>",
            "supplier": None, "sumber_supplier": None,
            "last_purchase_date": None, "last_purchase_rate": None,
            "total_qty": grand_qty, "total_penjualan": grand_amt,
        }
        for wh in warehouses:
            wh_key = wh.replace(" ", "_").replace("-", "_").replace(".", "_").lower()
            total_row["qty_" + wh_key] = sum(r.get("qty_" + wh_key, 0) for r in rows)
            total_row["amt_" + wh_key] = sum(r.get("amt_" + wh_key, 0) for r in rows)
        rows.append(total_row)
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
                "last_purchase_date": row["posting_date"], "last_purchase_rate": float(row.get("rate") or 0)}
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
                    "last_purchase_date": row["posting_date"], "last_purchase_rate": float(row.get("rate") or 0)}
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
