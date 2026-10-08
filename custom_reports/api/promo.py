import frappe
from frappe.utils import get_url
from custom_reports.api.outlets import resolve_warehouse_label

PRICE_LIST = "Standard Selling"

PROMO_FILTER_SQL = """
    pr.disable = 0
    AND pr.valid_from <= CURDATE()
    AND pr.valid_upto >= CURDATE()
    AND pr.price_or_product_discount = 'Price'
    AND pr.apply_on = 'Item Code'
    AND pr.coupon_code_based = 0
    AND (pr.min_qty IS NULL OR pr.min_qty <= 1)
    AND (pr.customer_group IS NULL OR pr.customer_group = '' OR pr.customer_group = 'All Customer Groups')
"""

PROMO_MAP_SUBQUERY = f"""
    (
        SELECT item_code, promo_name FROM (
            SELECT
                prc.item_code AS item_code,
                pr.name AS promo_name,
                ROW_NUMBER() OVER (PARTITION BY prc.item_code ORDER BY pr.modified DESC) AS rn
            FROM `tabPricing Rule Item Code` prc
            JOIN `tabPricing Rule` pr ON pr.name = prc.parent
            WHERE {PROMO_FILTER_SQL}
        ) ranked WHERE rn = 1
    )
"""


def _resolve_image(path):
    if not path:
        return None
    if path.startswith("http"):
        return path
    return get_url(path)


def resolve_party_label(customer, customer_group, territory):
    if customer:
        return f"Customer: {customer}"
    if customer_group and customer_group != "All Customer Groups":
        return f"Khusus: {customer_group}"
    if territory:
        return f"Wilayah: {territory}"
    return "Semua Pelanggan"


def compute_promo_price(original_price, rate_or_discount, discount_percentage, discount_amount, rate):
    if original_price is None:
        return None
    try:
        if rate_or_discount == "Discount Percentage" and discount_percentage:
            price = float(original_price) * (1 - float(discount_percentage) / 100)
        elif rate_or_discount == "Discount Amount" and discount_amount:
            price = float(original_price) - float(discount_amount)
        elif rate_or_discount == "Rate" and rate:
            price = float(rate)
        else:
            return None
        return max(0, round(price))
    except (TypeError, ValueError):
        return None


def _serialize_promo_item(row):
    original_price = row.get("price_list_rate")
    promo_price = compute_promo_price(
        original_price,
        row.get("rate_or_discount"),
        row.get("discount_percentage"),
        row.get("discount_amount"),
        row.get("rate"),
    )
    discount_pct = None
    if promo_price is not None and original_price:
        discount_pct = round((1 - promo_price / float(original_price)) * 100)

    return {
        "id": row.get("name"),
        "item_code": row.get("item_code"),
        "item_name": row.get("item_name"),
        "description": row.get("description"),
        "image": _resolve_image(row.get("image")),
        "department": row.get("department"),
        "category": row.get("category"),
        "sub_category": row.get("sub_category"),
        "original_price": original_price,
        "promo_price": promo_price,
        "discount_percentage": discount_pct,
        "promo_title": row.get("promo_title"),
        "warehouse_label": resolve_warehouse_label(row.get("warehouse")),
        "valid_upto": str(row.get("valid_upto")) if row.get("valid_upto") else None,
        "party_label": resolve_party_label(row.get("customer"), row.get("customer_group"), row.get("territory")),
    }


def _build_outlet_condition(outlet):
    """
    Resolve outlet filter into a SQL condition that respects warehouse
    hierarchy: a specific outlet also matches promos scoped to its parent
    department group (FASHION/FMCG) and promos scoped to "All Warehouses".
    Special values "ALL", "FMCG", "FASHION" filter at the group level directly.
    """
    if not outlet:
        return "", {}

    outlet_upper = outlet.upper()

    if outlet_upper == "ALL":
        return "AND (UPPER(pr.warehouse) LIKE %(w_all)s)", {"w_all": "%ALL WAREHOUSES%"}

    if outlet_upper in ("FMCG", "FASHION"):
        return (
            "AND (UPPER(pr.warehouse) LIKE %(w_group)s OR UPPER(pr.warehouse) LIKE %(w_all)s)",
            {"w_group": f"%{outlet_upper}%", "w_all": "%ALL WAREHOUSES%"},
        )

    parent = frappe.db.get_value("Outlet", outlet, "parent_outlet")
    parts = ["UPPER(pr.warehouse) LIKE %(w_code)s", "UPPER(pr.warehouse) LIKE %(w_all)s"]
    params = {"w_code": f"%{outlet_upper}%", "w_all": "%ALL WAREHOUSES%"}
    if parent:
        parts.append("UPPER(pr.warehouse) LIKE %(w_parent)s")
        params["w_parent"] = f"%{parent.upper()}%"
    return f"AND ({' OR '.join(parts)})", params


@frappe.whitelist(allow_guest=True)
def get_promo_items(department=None, category=None, sub_category=None, search=None, outlet=None, limit=12, offset=0):
    limit = int(limit)
    offset = int(offset)

    conditions = []
    values = {"price_list": PRICE_LIST, "limit": limit, "offset": offset}

    if department:
        conditions.append("AND i.department = %(department)s")
        values["department"] = department
    if category:
        conditions.append("AND i.category = %(category)s")
        values["category"] = category
    if sub_category:
        conditions.append("AND i.sub_category = %(sub_category)s")
        values["sub_category"] = sub_category
    if search:
        conditions.append("AND (i.item_name LIKE %(search)s OR i.description LIKE %(search)s)")
        values["search"] = f"%{search}%"
    if outlet:
        outlet_sql, outlet_params = _build_outlet_condition(outlet)
        conditions.append(outlet_sql)
        values.update(outlet_params)

    extra_where = " ".join(conditions)

    rows = frappe.db.sql(
        f"""
        SELECT
            i.name, i.item_code, i.item_name, i.description, i.image,
            i.department, i.category, i.sub_category,
            ip.price_list_rate,
            pr.title AS promo_title,
            pr.rate_or_discount, pr.discount_percentage, pr.discount_amount, pr.rate,
            pr.warehouse, pr.valid_upto, pr.customer, pr.customer_group, pr.territory
        FROM `tabItem` i
        JOIN {PROMO_MAP_SUBQUERY} promo_map ON promo_map.item_code = i.name
        JOIN `tabPricing Rule` pr ON pr.name = promo_map.promo_name
        LEFT JOIN `tabItem Price` ip
            ON ip.item_code = i.name
            AND ip.price_list = %(price_list)s
            AND ip.selling = 1
        WHERE i.disabled = 0 AND ip.price_list_rate IS NOT NULL {extra_where}
        ORDER BY pr.modified DESC
        LIMIT %(limit)s OFFSET %(offset)s
        """,
        values,
        as_dict=True,
    )
    items = [_serialize_promo_item(r) for r in rows]
    return [i for i in items if i["promo_price"] is not None]


@frappe.whitelist(allow_guest=True)
def get_promo_count():
    result = frappe.db.sql(
        f"""
        SELECT COUNT(DISTINCT i.name) as c
        FROM `tabItem` i
        JOIN {PROMO_MAP_SUBQUERY} promo_map ON promo_map.item_code = i.name
        LEFT JOIN `tabItem Price` ip
            ON ip.item_code = i.name AND ip.price_list = %(price_list)s AND ip.selling = 1
        WHERE i.disabled = 0 AND ip.price_list_rate IS NOT NULL
        """,
        {"price_list": PRICE_LIST},
        as_dict=True,
    )
    return result[0]["c"] if result else 0


@frappe.whitelist(allow_guest=True)
def get_promo_filters(department=None, category=None):
    base = f"""
        FROM `tabItem` i
        JOIN {PROMO_MAP_SUBQUERY} promo_map ON promo_map.item_code = i.name
        LEFT JOIN `tabItem Price` ip
            ON ip.item_code = i.name AND ip.price_list = %(price_list)s AND ip.selling = 1
        WHERE i.disabled = 0 AND ip.price_list_rate IS NOT NULL
    """
    values = {"price_list": PRICE_LIST}

    departments = frappe.db.sql(
        f"SELECT DISTINCT i.department {base} AND i.department IS NOT NULL AND i.department != '' ORDER BY i.department",
        values, as_dict=True,
    )

    cat_extra = ""
    cat_values = dict(values)
    if department:
        cat_extra = "AND i.department = %(department)s"
        cat_values["department"] = department
    categories = frappe.db.sql(
        f"SELECT DISTINCT i.category {base} AND i.category IS NOT NULL AND i.category != '' {cat_extra} ORDER BY i.category",
        cat_values, as_dict=True,
    )

    sub_extra_parts = []
    sub_values = dict(values)
    if department:
        sub_extra_parts.append("AND i.department = %(department)s")
        sub_values["department"] = department
    if category:
        sub_extra_parts.append("AND i.category = %(category)s")
        sub_values["category"] = category
    sub_extra = " ".join(sub_extra_parts)
    sub_categories = frappe.db.sql(
        f"SELECT DISTINCT i.sub_category {base} AND i.sub_category IS NOT NULL AND i.sub_category != '' {sub_extra} ORDER BY i.sub_category",
        sub_values, as_dict=True,
    )

    return {
        "departments": [d.department for d in departments],
        "categories": [c.category for c in categories],
        "sub_categories": [s.sub_category for s in sub_categories],
    }


@frappe.whitelist(allow_guest=True)
def get_item_promo(id):
    rows = frappe.db.sql(
        f"""
        SELECT
            i.name, i.item_code, i.item_name, i.description, i.image,
            i.department, i.category, i.sub_category,
            ip.price_list_rate,
            pr.title AS promo_title,
            pr.rate_or_discount, pr.discount_percentage, pr.discount_amount, pr.rate,
            pr.warehouse, pr.valid_upto, pr.customer, pr.customer_group, pr.territory
        FROM `tabItem` i
        JOIN {PROMO_MAP_SUBQUERY} promo_map ON promo_map.item_code = i.name
        JOIN `tabPricing Rule` pr ON pr.name = promo_map.promo_name
        LEFT JOIN `tabItem Price` ip
            ON ip.item_code = i.name
            AND ip.price_list = %(price_list)s
            AND ip.selling = 1
        WHERE i.disabled = 0 AND i.name = %(id)s AND ip.price_list_rate IS NOT NULL
        LIMIT 1
        """,
        {"price_list": PRICE_LIST, "id": id},
        as_dict=True,
    )
    if not rows:
        return None
    result = _serialize_promo_item(rows[0])
    return result if result["promo_price"] is not None else None
