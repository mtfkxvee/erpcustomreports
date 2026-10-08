import frappe
from frappe.utils import get_url

PRICE_LIST = "Standard Selling"


def _resolve_image(path):
    if not path:
        return None
    if path.startswith("http"):
        return path
    return get_url(path)


@frappe.whitelist(allow_guest=True)
def get_recommended_items(limit=8):
    limit = int(limit)

    # Ambil record WEBSITE X-SHA yang paling baru diupdate (sumber kebenaran tunggal)
    parent = frappe.db.sql(
        """
        SELECT name FROM `tabWEBSITE X-SHA`
        ORDER BY modified DESC
        LIMIT 1
        """,
        as_dict=True,
    )
    if not parent:
        return []

    parent_name = parent[0]["name"]

    chosen = frappe.db.sql(
        """
        SELECT item, idx
        FROM `tabCHOSEN PRODUCT WEB`
        WHERE parent = %(parent)s AND parenttype = 'WEBSITE X-SHA'
        ORDER BY idx ASC
        LIMIT %(limit)s
        """,
        {"parent": parent_name, "limit": limit},
        as_dict=True,
    )
    if not chosen:
        return []

    item_ids = [c["item"] for c in chosen if c["item"]]
    if not item_ids:
        return []

    placeholders = ", ".join(["%s"] * len(item_ids))
    rows = frappe.db.sql(
        f"""
        SELECT
            i.name, i.item_code, i.item_name, i.description, i.image,
            i.department, i.category, i.sub_category,
            ip.price_list_rate
        FROM `tabItem` i
        LEFT JOIN `tabItem Price` ip
            ON ip.item_code = i.name
            AND ip.price_list = %s
            AND ip.selling = 1
        WHERE i.name IN ({placeholders}) AND i.disabled = 0
        """,
        [PRICE_LIST] + item_ids,
        as_dict=True,
    )

    by_id = {r["name"]: r for r in rows}
    # Pertahankan urutan sesuai idx di child table, skip item yang gak ketemu/disabled
    ordered = [by_id[i] for i in item_ids if i in by_id]

    return [
        {
            "id": r["name"],
            "item_code": r.get("item_code"),
            "item_name": r.get("item_name"),
            "description": r.get("description"),
            "image": _resolve_image(r.get("image")),
            "department": r.get("department"),
            "category": r.get("category"),
            "sub_category": r.get("sub_category"),
            "standard_rate": r.get("price_list_rate"),
        }
        for r in ordered
    ]
