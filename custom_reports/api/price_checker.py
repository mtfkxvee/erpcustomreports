import frappe
from frappe.utils import get_url

PRICE_LIST = "Standard Selling"

def _resolve_image(path):
    if not path:
        return None
    if path.startswith("http"):
        return path
    return get_url(path)

def _resolve_item_code(query):
    # 1. exact barcode match (tabItem Barcode)
    item_code = frappe.db.get_value("Item Barcode", {"barcode": query}, "parent")
    if item_code:
        return item_code

    # 2. exact item_code match
    if frappe.db.exists("Item", query):
        return query

    # 3. fuzzy match by item_name atau item_code (item aktif duluan, exact dulu)
    rows = frappe.db.sql(
        """
        SELECT name
        FROM `tabItem`
        WHERE disabled = 0
          AND (item_name LIKE %(q)s OR item_code LIKE %(q)s)
        ORDER BY
          CASE WHEN item_code = %(exact)s THEN 0 ELSE 1 END,
          modified DESC
        LIMIT 1
        """,
        {"q": f"%{query}%", "exact": query},
        as_dict=True,
    )
    return rows[0].name if rows else None

def _get_stock_summary(item_code):
    rows = frappe.db.sql(
        """
        SELECT warehouse, actual_qty
        FROM `tabBin`
        WHERE item_code = %(item_code)s AND actual_qty > 0
        """,
        {"item_code": item_code},
        as_dict=True,
    )
    total_qty = sum(r.actual_qty for r in rows)
    warehouses = [{"warehouse": r.warehouse, "qty": r.actual_qty} for r in rows]
    return {"total_qty": total_qty, "warehouses": warehouses}

@frappe.whitelist(allow_guest=True)
def lookup_item(query="", outlet=None):
    query = (query or "").strip()
    if not query:
        frappe.throw("Masukkan barcode atau nama barang")

    item_code = _resolve_item_code(query)
    if not item_code:
        return {"found": False}

    row = frappe.db.sql(
        """
        SELECT
            i.name, i.item_code, i.item_name, i.image, i.stock_uom,
            ip.price_list_rate
        FROM `tabItem` i
        LEFT JOIN `tabItem Price` ip
            ON ip.item_code = i.name
            AND ip.price_list = %(price_list)s
            AND ip.selling = 1
        WHERE i.name = %(item_code)s AND i.disabled = 0
        LIMIT 1
        """,
        {"price_list": PRICE_LIST, "item_code": item_code},
        as_dict=True,
    )
    if not row:
        return {"found": False}

    item = row[0]
    stock = _get_stock_summary(item.item_code)

    # NOTE: belum ada mapping outlet (custom_outlet di Sales Invoice) <-> nama
    # warehouse yang terverifikasi, jadi stok yang dibalikin masih total semua
    # warehouse. Param `outlet` di-terima tapi belum dipakai buat filter.

    return {
        "found": True,
        "item_code": item.item_code,
        "item_name": item.item_name,
        "image": _resolve_image(item.image),
        "price": item.price_list_rate,
        "price_list": PRICE_LIST,
        "stock_uom": item.stock_uom,
        "stock_qty": stock["total_qty"],
        "warehouses": stock["warehouses"],
    }
