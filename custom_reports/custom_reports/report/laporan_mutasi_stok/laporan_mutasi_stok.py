import frappe
from frappe import _
from frappe.utils import flt


def get_warehouse_list(warehouse):
    """Expand warehouse ke semua child."""
    if not warehouse:
        return []
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
        {"fieldname": "item_code",          "label": _("Kode Item"),          "fieldtype": "Link",     "options": "Item", "width": 130},
        {"fieldname": "item_name",          "label": _("Nama Item"),          "fieldtype": "Data",     "width": 200},
        {"fieldname": "item_group",         "label": _("Item Group"),         "fieldtype": "Data",     "width": 130},
        {"fieldname": "warehouse",          "label": _("Warehouse"),          "fieldtype": "Data",     "width": 160},
        {"fieldname": "uom",                "label": _("UOM"),                "fieldtype": "Data",     "width": 60},
        {"fieldname": "saldo_awal",         "label": _("Saldo Awal (Qty)"),   "fieldtype": "Float",    "width": 110},
        {"fieldname": "saldo_awal_val",     "label": _("Saldo Awal (Rp)"),    "fieldtype": "Currency", "width": 130},
        {"fieldname": "pembelian",          "label": _("Pembelian (Qty)"),    "fieldtype": "Float",    "width": 110},
        {"fieldname": "pembelian_val",      "label": _("Pembelian (Rp)"),     "fieldtype": "Currency", "width": 130},
        {"fieldname": "penjualan",          "label": _("Penjualan (Qty)"),    "fieldtype": "Float",    "width": 110},
        {"fieldname": "penjualan_val",      "label": _("Penjualan (Rp)"),     "fieldtype": "Currency", "width": 130},
        {"fieldname": "transfer_masuk",     "label": _("Transfer Masuk (Qty)"),  "fieldtype": "Float",    "width": 130},
        {"fieldname": "transfer_masuk_val", "label": _("Transfer Masuk (Rp)"),   "fieldtype": "Currency", "width": 140},
        {"fieldname": "transfer_keluar",    "label": _("Transfer Keluar (Qty)"), "fieldtype": "Float",    "width": 130},
        {"fieldname": "transfer_keluar_val","label": _("Transfer Keluar (Rp)"),  "fieldtype": "Currency", "width": 140},
        {"fieldname": "lainnya",            "label": _("Lainnya (Qty)"),      "fieldtype": "Float",    "width": 110},
        {"fieldname": "lainnya_val",        "label": _("Lainnya (Rp)"),       "fieldtype": "Currency", "width": 130},
        {"fieldname": "saldo_akhir",        "label": _("Saldo Akhir (Qty)"),  "fieldtype": "Float",    "width": 110},
        {"fieldname": "saldo_akhir_val",    "label": _("Saldo Akhir (Rp)"),   "fieldtype": "Currency", "width": 130},
    ]


def get_data(filters):
    from_date  = filters["from_date"]
    to_date    = filters["to_date"]
    warehouse  = filters.get("warehouse")
    item_code  = filters.get("item_code")
    item_group = filters.get("item_group")

    wh_list = get_warehouse_list(warehouse)

    # Build conditions
    wh_cond = ""
    if wh_list:
        if len(wh_list) == 1:
            wh_cond = "AND sle.warehouse = '{}'".format(wh_list[0].replace("'","''"))
        else:
            wh_str = ", ".join(["'{}'".format(w.replace("'","''")) for w in wh_list])
            wh_cond = "AND sle.warehouse IN ({})".format(wh_str)

    item_cond = ""
    if item_code:
        item_cond = "AND sle.item_code = '{}'".format(item_code.replace("'","''"))

    ig_cond = ""
    if item_group:
        ig_cond = "AND i.item_group = '{}'".format(item_group.replace("'","''"))

    # Query saldo awal (sebelum from_date)
    sql_awal = """
        SELECT item_code, warehouse, qty_after_transaction as qty, stock_value as val
        FROM (
            SELECT s.item_code, s.warehouse,
                   s.qty_after_transaction, s.stock_value,
                   ROW_NUMBER() OVER (
                       PARTITION BY s.item_code, s.warehouse
                       ORDER BY s.posting_date DESC, s.posting_time DESC, s.creation DESC
                   ) as rn
            FROM `tabStock Ledger Entry` s
            JOIN `tabItem` i ON i.name = s.item_code
            WHERE s.is_cancelled = 0
            AND s.posting_date < %(from_date)s
            {wh_cond} {item_cond} {ig_cond}
        ) ranked
        WHERE rn = 1
    """.format(wh_cond=wh_cond.replace("sle.", "s."), item_cond=item_cond.replace("sle.", "s."), ig_cond=ig_cond.replace("i.", "i."))

    # Query mutasi dalam periode - pisah masuk/keluar per baris agar akurat.
    # Untuk voucher_type Stock Reconciliation, actual_qty ERPNext memang selalu 0
    # (by-design, non-serial/non-batch) sehingga tidak bisa dipakai untuk qty movement.
    # qty_diff dihitung sebagai delta qty_after_transaction terhadap baris sebelumnya
    # (per item+warehouse, urut kronologis), mengikuti pola stock_balance.py bawaan ERPNext.
    # LAG dihitung atas semua baris sampai to_date (bukan dibatasi from_date) supaya baris
    # Stock Reconciliation pertama dalam periode tetap dapat saldo sebelumnya yang benar.
    sql_mutasi = """
        SELECT item_code, warehouse, voucher_type,
               SUM(qty_diff) as qty,
               SUM(stock_value_difference) as val,
               SUM(CASE WHEN qty_diff > 0 THEN stock_value_difference ELSE 0 END) as val_masuk,
               SUM(CASE WHEN qty_diff < 0 THEN stock_value_difference ELSE 0 END) as val_keluar,
               SUM(CASE WHEN qty_diff > 0 THEN qty_diff ELSE 0 END) as qty_masuk,
               SUM(CASE WHEN qty_diff < 0 THEN qty_diff ELSE 0 END) as qty_keluar
        FROM (
            SELECT sle.item_code, sle.warehouse, sle.voucher_type, sle.posting_date,
                   sle.stock_value_difference,
                   CASE
                       WHEN sle.voucher_type = 'Stock Reconciliation'
                       THEN sle.qty_after_transaction - COALESCE(
                           LAG(sle.qty_after_transaction) OVER (
                               PARTITION BY sle.item_code, sle.warehouse
                               ORDER BY sle.posting_date, sle.posting_time, sle.creation
                           ), 0)
                       ELSE sle.actual_qty
                   END as qty_diff
            FROM `tabStock Ledger Entry` sle
            JOIN `tabItem` i ON i.name = sle.item_code
            WHERE sle.is_cancelled = 0
            AND sle.posting_date <= %(to_date)s
            {wh_cond} {item_cond} {ig_cond}
        ) x
        WHERE posting_date BETWEEN %(from_date)s AND %(to_date)s
        GROUP BY item_code, warehouse, voucher_type
    """.format(wh_cond=wh_cond, item_cond=item_cond, ig_cond=ig_cond)

    values = {"from_date": from_date, "to_date": to_date}

    awal_rows   = frappe.db.sql(sql_awal,   values, as_dict=True)
    mutasi_rows = frappe.db.sql(sql_mutasi, values, as_dict=True)

    # Build map saldo awal
    awal_map = {}
    for r in awal_rows:
        awal_map[(r.item_code, r.warehouse)] = {"qty": flt(r.qty), "val": flt(r.val)}

    # Build map mutasi
    mutasi_map = {}
    for r in mutasi_rows:
        key = (r.item_code, r.warehouse)
        if key not in mutasi_map:
            mutasi_map[key] = {
                "pembelian": 0, "pembelian_val": 0,
                "penjualan": 0, "penjualan_val": 0,
                "transfer_masuk": 0, "transfer_masuk_val": 0,
                "transfer_keluar": 0, "transfer_keluar_val": 0,
                "lainnya": 0, "lainnya_val": 0
            }
        qty        = flt(r.qty)
        val        = flt(r.val)
        val_masuk  = flt(r.val_masuk)
        val_keluar = flt(r.val_keluar)
        qty_masuk  = flt(r.qty_masuk)
        qty_keluar = flt(r.qty_keluar)
        vt         = r.voucher_type

        if vt in ("Purchase Invoice", "Purchase Receipt"):
            if qty_masuk > 0:
                mutasi_map[key]["pembelian"]     += qty_masuk
                mutasi_map[key]["pembelian_val"] += val_masuk
            if qty_keluar < 0:
                mutasi_map[key]["lainnya"]     += qty_keluar
                mutasi_map[key]["lainnya_val"] += val_keluar
        elif vt == "Sales Invoice":
            mutasi_map[key]["penjualan"]     += qty
            mutasi_map[key]["penjualan_val"] += val
        elif vt == "Stock Entry":
            mutasi_map[key]["transfer_masuk"]     += qty_masuk
            mutasi_map[key]["transfer_masuk_val"] += val_masuk
            mutasi_map[key]["transfer_keluar"]     += abs(qty_keluar)
            mutasi_map[key]["transfer_keluar_val"] += abs(val_keluar)
        else:
            mutasi_map[key]["lainnya"]     += qty
            mutasi_map[key]["lainnya_val"] += val

    # Gabungkan semua keys
    all_keys = set(list(awal_map.keys()) + list(mutasi_map.keys()))

    # Ambil info item
    item_info = {}
    all_items = list(set([k[0] for k in all_keys]))
    if all_items:
        items = frappe.db.sql("""
            SELECT name, item_name, item_group, stock_uom
            FROM `tabItem` WHERE name IN ({})
        """.format(", ".join(["'{}'".format(i.replace("'","''")) for i in all_items])), as_dict=True)
        for item in items:
            item_info[item.name] = item

    rows = []
    grand = {
        "saldo_awal": 0, "saldo_awal_val": 0,
        "pembelian": 0, "pembelian_val": 0,
        "penjualan": 0, "penjualan_val": 0,
        "transfer_masuk": 0, "transfer_masuk_val": 0,
        "transfer_keluar": 0, "transfer_keluar_val": 0,
        "lainnya": 0, "lainnya_val": 0,
        "saldo_akhir": 0, "saldo_akhir_val": 0,
    }

    for key in sorted(all_keys):
        item_code_k, warehouse_k = key
        info    = item_info.get(item_code_k, {})
        awal_data = awal_map.get(key, {"qty": 0, "val": 0})
        awal      = flt(awal_data["qty"])
        awal_val  = flt(awal_data["val"])
        mutasi    = mutasi_map.get(key, {})

        pembelian           = flt(mutasi.get("pembelian", 0))
        pembelian_val       = flt(mutasi.get("pembelian_val", 0))
        penjualan           = flt(mutasi.get("penjualan", 0))
        penjualan_val       = flt(mutasi.get("penjualan_val", 0))
        transfer_masuk      = flt(mutasi.get("transfer_masuk", 0))
        transfer_masuk_val  = flt(mutasi.get("transfer_masuk_val", 0))
        transfer_keluar     = flt(mutasi.get("transfer_keluar", 0))
        transfer_keluar_val = flt(mutasi.get("transfer_keluar_val", 0))
        lainnya             = flt(mutasi.get("lainnya", 0))
        lainnya_val         = flt(mutasi.get("lainnya_val", 0))

        saldo_akhir     = awal + pembelian + penjualan + transfer_masuk - transfer_keluar + lainnya
        saldo_akhir_val = awal_val + pembelian_val + penjualan_val + transfer_masuk_val - transfer_keluar_val + lainnya_val

        # Skip baris yang semua 0
        if not any([awal, pembelian, penjualan, transfer_masuk, transfer_keluar, lainnya]):
            continue

        rows.append({
            "item_code":           item_code_k,
            "item_name":           info.get("item_name", ""),
            "item_group":          info.get("item_group", ""),
            "warehouse":           warehouse_k,
            "uom":                 info.get("stock_uom", ""),
            "saldo_awal":          awal,
            "saldo_awal_val":      awal_val,
            "pembelian":           pembelian,
            "pembelian_val":       pembelian_val,
            "penjualan":           penjualan,
            "penjualan_val":       penjualan_val,
            "transfer_masuk":      transfer_masuk,
            "transfer_masuk_val":  transfer_masuk_val,
            "transfer_keluar":     transfer_keluar,
            "transfer_keluar_val": transfer_keluar_val,
            "lainnya":             lainnya,
            "lainnya_val":         lainnya_val,
            "saldo_akhir":         saldo_akhir,
            "saldo_akhir_val":     saldo_akhir_val,
        })

        grand["saldo_awal"]          += awal
        grand["saldo_awal_val"]      += awal_val
        grand["pembelian"]           += pembelian
        grand["pembelian_val"]       += pembelian_val
        grand["penjualan"]           += penjualan
        grand["penjualan_val"]       += penjualan_val
        grand["transfer_masuk"]      += transfer_masuk
        grand["transfer_masuk_val"]  += transfer_masuk_val
        grand["transfer_keluar"]     += transfer_keluar
        grand["transfer_keluar_val"] += transfer_keluar_val
        grand["lainnya"]             += lainnya
        grand["lainnya_val"]         += lainnya_val
        grand["saldo_akhir"]         += saldo_akhir
        grand["saldo_akhir_val"]     += saldo_akhir_val

    # Total row
    if rows:
        rows.append({
            "item_code":           "<b>TOTAL</b>",
            "item_name":           "",
            "item_group":          "",
            "warehouse":           "",
            "uom":                 "",
            "saldo_awal":          grand["saldo_awal"],
            "saldo_awal_val":      grand["saldo_awal_val"],
            "pembelian":           grand["pembelian"],
            "pembelian_val":       grand["pembelian_val"],
            "penjualan":           grand["penjualan"],
            "penjualan_val":       grand["penjualan_val"],
            "transfer_masuk":      grand["transfer_masuk"],
            "transfer_masuk_val":  grand["transfer_masuk_val"],
            "transfer_keluar":     grand["transfer_keluar"],
            "transfer_keluar_val": grand["transfer_keluar_val"],
            "lainnya":             grand["lainnya"],
            "lainnya_val":         grand["lainnya_val"],
            "saldo_akhir":         grand["saldo_akhir"],
            "saldo_akhir_val":     grand["saldo_akhir_val"],
        })

    return rows
