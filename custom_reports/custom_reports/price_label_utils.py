import frappe
from frappe.utils import today
from frappe.utils import flt


@frappe.whitelist()
def get_discounted_price(item_code, item_group, normal_price, price_list=None):
    """Cari pricing rule aktif untuk item dan hitung harga diskon."""
    normal_price = flt(normal_price)
    td = today()

    # Cek by item code dulu
    rules = frappe.db.sql("""
        SELECT pr.name, pr.discount_percentage, pr.discount_amount, pr.rate
        FROM `tabPricing Rule` pr
        JOIN `tabPricing Rule Item Code` pric ON pric.parent = pr.name
        WHERE pric.item_code = %s
        AND pr.disable = 0
        AND pr.selling = 1
        AND pr.price_or_product_discount = 'Price'
        AND (pr.valid_from IS NULL OR pr.valid_from <= %s)
        AND (pr.valid_upto IS NULL OR pr.valid_upto >= %s)
        ORDER BY pr.priority DESC
        LIMIT 1
    """, (item_code, td, td), as_dict=True)

    # Fallback ke item group
    if not rules and item_group:
        rules = frappe.db.sql("""
            SELECT pr.name, pr.discount_percentage, pr.discount_amount, pr.rate
            FROM `tabPricing Rule` pr
            JOIN `tabPricing Rule Item Group` prig ON prig.parent = pr.name
            WHERE prig.item_group = %s
            AND pr.disable = 0
            AND pr.selling = 1
            AND pr.price_or_product_discount = 'Price'
            AND (pr.valid_from IS NULL OR pr.valid_from <= %s)
            AND (pr.valid_upto IS NULL OR pr.valid_upto >= %s)
            ORDER BY pr.priority DESC
            LIMIT 1
        """, (item_group, td, td), as_dict=True)

    if not rules:
        return 0

    pr = rules[0]
    discounted = normal_price

    if flt(pr.discount_percentage) > 0:
        discounted = normal_price * (1 - flt(pr.discount_percentage) / 100)
    elif flt(pr.discount_amount) > 0:
        discounted = normal_price - flt(pr.discount_amount)
    elif flt(pr.rate) > 0:
        discounted = flt(pr.rate)

    return round(discounted)
