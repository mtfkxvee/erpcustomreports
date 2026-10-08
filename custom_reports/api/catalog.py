import frappe
from frappe.utils import get_url

PRICE_LIST = "Standard Selling"


def _resolve_image(path):
    if not path:
        return None
    if path.startswith("http"):
        return path
    return get_url(path)


def _serialize_item(row):
    return {
        "id": row.get("name"),
        "item_code": row.get("item_code"),
        "item_name": row.get("item_name"),
        "description": row.get("description"),
        "image": _resolve_image(row.get("image")),
        "department": row.get("department"),
        "category": row.get("category"),
        "sub_category": row.get("sub_category"),
        "standard_rate": row.get("price_list_rate"),
    }


@frappe.whitelist(allow_guest=True)
def get_catalog_items(department=None, category=None, sub_category=None, search=None, limit=24, offset=0):
    limit = int(limit)
    offset = int(offset)

    conditions = ["i.disabled = 0"]
    values = {}

    if department:
        conditions.append("i.department = %(department)s")
        values["department"] = department
    if category:
        conditions.append("i.category = %(category)s")
        values["category"] = category
    if sub_category:
        conditions.append("i.sub_category = %(sub_category)s")
        values["sub_category"] = sub_category
    if search:
        conditions.append("(i.item_name LIKE %(search)s OR i.description LIKE %(search)s)")
        values["search"] = f"%{search}%"

    where_clause = " AND ".join(conditions)
    values["price_list"] = PRICE_LIST
    values["limit"] = limit
    values["offset"] = offset

    rows = frappe.db.sql(
        f"""
        SELECT
            i.name, i.item_code, i.item_name, i.description, i.image,
            i.department, i.category, i.sub_category,
            ip.price_list_rate
        FROM `tabItem` i
        LEFT JOIN `tabItem Price` ip
            ON ip.item_code = i.name
            AND ip.price_list = %(price_list)s
            AND ip.selling = 1
        WHERE {where_clause}
        ORDER BY i.item_name
        LIMIT %(limit)s OFFSET %(offset)s
        """,
        values,
        as_dict=True,
    )
    return [_serialize_item(r) for r in rows]


@frappe.whitelist(allow_guest=True)
def get_catalog_item(id):
    row = frappe.db.sql(
        """
        SELECT
            i.name, i.item_code, i.item_name, i.description, i.image,
            i.department, i.category, i.sub_category,
            ip.price_list_rate
        FROM `tabItem` i
        LEFT JOIN `tabItem Price` ip
            ON ip.item_code = i.name
            AND ip.price_list = %(price_list)s
            AND ip.selling = 1
        WHERE i.name = %(id)s AND i.disabled = 0
        LIMIT 1
        """,
        {"price_list": PRICE_LIST, "id": id},
        as_dict=True,
    )
    if not row:
        frappe.throw("Item not found", frappe.DoesNotExistError)
    return _serialize_item(row[0])


@frappe.whitelist(allow_guest=True)
def get_related_catalog_items(id, sub_category, limit=4):
    limit = int(limit)
    rows = frappe.db.sql(
        """
        SELECT
            i.name, i.item_code, i.item_name, i.description, i.image,
            i.department, i.category, i.sub_category,
            ip.price_list_rate
        FROM `tabItem` i
        LEFT JOIN `tabItem Price` ip
            ON ip.item_code = i.name
            AND ip.price_list = %(price_list)s
            AND ip.selling = 1
        WHERE i.disabled = 0
            AND i.sub_category = %(sub_category)s
            AND i.name != %(id)s
        LIMIT %(limit)s
        """,
        {"price_list": PRICE_LIST, "sub_category": sub_category, "id": id, "limit": limit},
        as_dict=True,
    )
    return [_serialize_item(r) for r in rows]


@frappe.whitelist(allow_guest=True)
def get_catalog_filters(department=None, category=None):
    departments = frappe.db.sql(
        "SELECT DISTINCT department FROM `tabItem` WHERE disabled = 0 AND department IS NOT NULL AND department != '' ORDER BY department",
        as_dict=True,
    )

    cat_conditions = ["disabled = 0", "category IS NOT NULL", "category != ''"]
    cat_values = {}
    if department:
        cat_conditions.append("department = %(department)s")
        cat_values["department"] = department
    categories = frappe.db.sql(
        f"SELECT DISTINCT category FROM `tabItem` WHERE {' AND '.join(cat_conditions)} ORDER BY category",
        cat_values,
        as_dict=True,
    )

    sub_conditions = ["disabled = 0", "sub_category IS NOT NULL", "sub_category != ''"]
    sub_values = {}
    if department:
        sub_conditions.append("department = %(department)s")
        sub_values["department"] = department
    if category:
        sub_conditions.append("category = %(category)s")
        sub_values["category"] = category
    sub_categories = frappe.db.sql(
        f"SELECT DISTINCT sub_category FROM `tabItem` WHERE {' AND '.join(sub_conditions)} ORDER BY sub_category",
        sub_values,
        as_dict=True,
    )

    return {
        "departments": [d.department for d in departments],
        "categories": [c.category for c in categories],
        "sub_categories": [s.sub_category for s in sub_categories],
    }
