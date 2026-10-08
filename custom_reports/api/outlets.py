import re
import json
import frappe

STOPWORDS = {"X", "SHA", "SHAMART", "MART", "TOKO", "SHOP", "BILLING", "GUDANG",
             "SELLING", "AREA", "STORE"}


def _tokens(text):
    text = (text or "").upper()
    parts = re.split(r"[^A-Z0-9]+", text)
    return {p for p in parts if p and p not in STOPWORDS}


def _exact_overlap(a_tokens, b_tokens):
    return len(a_tokens & b_tokens)


def _fuzzy_overlap(a_tokens, b_tokens):
    score = 0
    for a in a_tokens:
        for b in b_tokens:
            if a == b:
                continue
            # Only allow substring matches for reasonably long, distinctive tokens
            # to avoid short accidental matches (e.g. "SP" inside "PUSPAHIANG").
            shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
            if len(shorter) >= 4 and shorter in longer:
                score += 1
    return score


def _parse_latlng(geojson_str):
    if not geojson_str:
        return None, None
    try:
        data = json.loads(geojson_str)
        coords = data["features"][0]["geometry"]["coordinates"]
        return coords[1], coords[0]  # lat, lng
    except Exception:
        return None, None


@frappe.whitelist(allow_guest=True)
def get_website_outlets():
    outlets = frappe.get_all(
        "Outlet",
        filters={"is_active": 1, "tampilkan_di_website": 1, "is_group": 0},
        fields=["kode", "nama", "city", "warehouse", "lokasi"],
        order_by="nama",
    )

    address_names = frappe.get_all(
        "Dynamic Link",
        filters={"link_doctype": "Company", "link_name": "X-SHA", "parenttype": "Address"},
        pluck="parent",
    )
    addresses = frappe.get_all(
        "Address",
        filters={"name": ["in", address_names], "disabled": 0},
        fields=["address_title", "address_line1", "address_line2", "city", "phone"],
    )

    results = []
    for o in outlets:
        o_tokens = _tokens(o.nama)

        # Tier 1: exact token overlap (most reliable).
        best_addr = None
        best_score = 0
        for addr in addresses:
            a_tokens = _tokens(addr.address_title)
            score = _exact_overlap(o_tokens, a_tokens)
            if score > best_score:
                best_score = score
                best_addr = addr

        # Tier 2: only fall back to fuzzy substring matching if NO exact
        # match was found at all (avoids false positives like "SP" inside
        # "PUSPAHIANG" beating a real exact match).
        if best_addr is None:
            for addr in addresses:
                a_tokens = _tokens(addr.address_title)
                score = _fuzzy_overlap(o_tokens, a_tokens)
                if score > best_score:
                    best_score = score
                    best_addr = addr

        lat, lng = _parse_latlng(o.lokasi)

        results.append({
            "kode": o.kode,
            "nama": o.nama,
            "city": (best_addr.city if best_addr else o.city),
            "warehouse": o.warehouse,
            "address_line1": best_addr.address_line1 if best_addr else None,
            "address_line2": best_addr.address_line2 if best_addr else None,
            "phone": best_addr.phone if best_addr else None,
            "lat": lat,
            "lng": lng,
        })
    return results


def resolve_warehouse_label(warehouse):
    """Resolve a Pricing Rule warehouse value to a human-friendly outlet label,
    using live Outlet doctype data (exact match first, then code-prefix fallback,
    then department-group fallback)."""
    if not warehouse:
        return "Semua Outlet"

    w = warehouse.upper()
    if "ALL WAREHOUSES" in w:
        return "Semua Outlet"

    outlets = frappe.get_all(
        "Outlet",
        filters={"is_group": 0},
        fields=["kode", "nama", "warehouse"],
    )

    # 1. Exact match on warehouse field.
    for o in outlets:
        if o.warehouse and o.warehouse.upper() == w:
            return o.nama

    # 2. Code-prefix fallback (e.g. "XJB - X" or "HCW - X" without "SELLING AREA").
    for o in outlets:
        if o.kode and o.kode.upper() in w:
            return o.nama

    # 3. Department-group fallback.
    if "FASHION" in w:
        return "Semua Outlet (Fashion & Home Supplies)"
    if "FMCG" in w:
        return "Semua Outlet (FMCG)"

    return warehouse
