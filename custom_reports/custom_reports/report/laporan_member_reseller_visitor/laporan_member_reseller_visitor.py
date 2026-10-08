import frappe
from frappe import _
from frappe.utils import flt


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
            children = frappe.db.get_all("Outlet", filters={"parent_outlet": current}, fields=["name"])
            for c in children:
                queue.append(c["name"])
    return result


def get_outlet_list(filters):
    outlet_raw = filters.get("outlet")
    if not outlet_raw:
        return [o.name for o in frappe.get_all("Outlet", filters={"is_group": 0})]
    values = outlet_raw if isinstance(outlet_raw, list) else [outlet_raw]
    result = []
    for o in values:
        name = o.get("value") if isinstance(o, dict) else str(o)
        for c in get_outlet_children(name):
            if c not in result:
                result.append(c)
    return result or [o.name for o in frappe.get_all("Outlet", filters={"is_group": 0})]


def get_customer_group_children(customer_group):
    result = []
    queue = [customer_group]
    while queue:
        current = queue.pop(0)
        cg = frappe.db.get_value("Customer Group", current, ["is_group", "name"], as_dict=True)
        if not cg:
            continue
        result.append(current)
        if cg.is_group:
            children = frappe.db.get_all("Customer Group", filters={"parent_customer_group": current}, fields=["name"])
            for c in children:
                queue.append(c["name"])
    return result


def get_customer_group_list(filters):
    cg_raw = filters.get("customer_group")
    if not cg_raw:
        default_groups = ["MEMBER", "Reseller"]
        return [g for g in default_groups if frappe.db.exists("Customer Group", g)]
    values = cg_raw if isinstance(cg_raw, list) else [cg_raw]
    result = []
    for g in values:
        name = g.get("value") if isinstance(g, dict) else str(g)
        for c in get_customer_group_children(name):
            if c not in result:
                result.append(c)
    return result


def execute(filters=None):
    filters = filters or {}
    if not filters.get("from_date") or not filters.get("to_date"):
        frappe.msgprint(_("Silakan pilih Dari Tanggal dan Sampai Tanggal."), indicator="orange", alert=True)
        return [], []

    outlets = get_outlet_list(filters)
    customer_groups = get_customer_group_list(filters)
    if not outlets or not customer_groups:
        return get_columns(), []

    values = {
        "from_date": filters["from_date"],
        "to_date": filters["to_date"],
        "outlets": outlets,
        "customer_groups": customer_groups,
    }

    columns = get_columns()
    data = get_data(values)
    chart = get_chart(data)
    summary = get_summary(data)
    return columns, data, None, chart, summary


def get_columns():
    return [
        {"fieldname": "outlet", "label": _("Outlet"), "fieldtype": "Link", "options": "Outlet", "width": 130},
        {"fieldname": "customer_baru", "label": _("Customer Baru"), "fieldtype": "Int", "width": 120},
        {"fieldname": "member_aktif", "label": _("Member Aktif"), "fieldtype": "Int", "width": 120},
        {"fieldname": "visitor", "label": _("Visitor"), "fieldtype": "Int", "width": 100},
        {"fieldname": "transaksi", "label": _("Jumlah Transaksi"), "fieldtype": "Int", "width": 130},
        {"fieldname": "frekuensi_kunjungan", "label": _("Frekuensi Kunjungan"), "fieldtype": "Float", "precision": 2, "width": 150},
        {"fieldname": "repeat_order", "label": _("Repeat Order"), "fieldtype": "Int", "width": 120},
        {"fieldname": "penjualan", "label": _("Penjualan (Rp)"), "fieldtype": "Currency", "width": 160},
    ]


def get_data(values):
    visitor_map = get_visitor_map(values)
    sales_map = get_sales_map(values)
    repeat_map = get_repeat_map(values)
    new_customer_map = get_new_customer_map(values)

    rows = []
    grand = {"customer_baru": 0, "member_aktif": 0, "visitor": 0, "transaksi": 0, "repeat_order": 0, "penjualan": 0}

    for outlet in values["outlets"]:
        sales = sales_map.get(outlet, {"transaksi": 0, "member_aktif": 0, "penjualan": 0})
        visitor = visitor_map.get(outlet, 0)
        repeat_order = repeat_map.get(outlet, 0)
        customer_baru = new_customer_map.get(outlet, 0)
        transaksi = sales["transaksi"]
        member_aktif = sales["member_aktif"]
        frekuensi = (transaksi / member_aktif) if member_aktif else 0

        if not any([customer_baru, member_aktif, visitor, transaksi, repeat_order, sales["penjualan"]]):
            continue

        rows.append({
            "outlet": outlet,
            "customer_baru": customer_baru,
            "member_aktif": member_aktif,
            "visitor": visitor,
            "transaksi": transaksi,
            "frekuensi_kunjungan": frekuensi,
            "repeat_order": repeat_order,
            "penjualan": sales["penjualan"],
        })

        grand["customer_baru"] += customer_baru
        grand["member_aktif"] += member_aktif
        grand["visitor"] += visitor
        grand["transaksi"] += transaksi
        grand["repeat_order"] += repeat_order
        grand["penjualan"] += sales["penjualan"]

    rows.sort(key=lambda r: r["penjualan"], reverse=True)

    if rows:
        grand_frekuensi = (grand["transaksi"] / grand["member_aktif"]) if grand["member_aktif"] else 0
        rows.append({
            "outlet": "<b>TOTAL</b>",
            "customer_baru": grand["customer_baru"],
            "member_aktif": grand["member_aktif"],
            "visitor": grand["visitor"],
            "transaksi": grand["transaksi"],
            "frekuensi_kunjungan": grand_frekuensi,
            "repeat_order": grand["repeat_order"],
            "penjualan": grand["penjualan"],
        })

    return rows


def get_visitor_map(values):
    rows = frappe.db.sql("""
        SELECT pp.custom_outlet as outlet, SUM(pcs.visitor) as visitor
        FROM `tabPOS Closing Shift` pcs
        JOIN `tabPOS Profile` pp ON pp.name = pcs.pos_profile
        WHERE pcs.docstatus = 1
        AND pcs.posting_date BETWEEN %(from_date)s AND %(to_date)s
        AND pp.custom_outlet IN %(outlets)s
        GROUP BY pp.custom_outlet
    """, values, as_dict=True)
    return {r.outlet: flt(r.visitor) for r in rows}


def get_sales_map(values):
    rows = frappe.db.sql("""
        SELECT si.custom_outlet as outlet,
               COUNT(*) as transaksi,
               COUNT(DISTINCT si.customer) as member_aktif,
               SUM(si.grand_total) as penjualan
        FROM `tabSales Invoice` si
        WHERE si.docstatus = 1
        AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
        AND si.custom_outlet IN %(outlets)s
        AND si.customer_group IN %(customer_groups)s
        GROUP BY si.custom_outlet
    """, values, as_dict=True)
    return {
        r.outlet: {"transaksi": int(r.transaksi), "member_aktif": int(r.member_aktif), "penjualan": flt(r.penjualan)}
        for r in rows
    }


def get_repeat_map(values):
    rows = frappe.db.sql("""
        SELECT outlet, COUNT(*) as repeat_customers FROM (
            SELECT si.custom_outlet as outlet, si.customer, COUNT(*) as cnt
            FROM `tabSales Invoice` si
            WHERE si.docstatus = 1
            AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
            AND si.custom_outlet IN %(outlets)s
            AND si.customer_group IN %(customer_groups)s
            GROUP BY si.custom_outlet, si.customer
            HAVING COUNT(*) > 1
        ) t GROUP BY outlet
    """, values, as_dict=True)
    return {r.outlet: int(r.repeat_customers) for r in rows}


def get_new_customer_map(values):
    new_customers = frappe.db.sql("""
        SELECT name FROM `tabCustomer`
        WHERE DATE(creation) BETWEEN %(from_date)s AND %(to_date)s
        AND customer_group IN %(customer_groups)s
    """, values, as_dict=True)
    if not new_customers:
        return {}
    customer_names = [r.name for r in new_customers]

    rows = frappe.db.sql("""
        SELECT customer, custom_outlet FROM (
            SELECT si.customer, si.custom_outlet,
                   ROW_NUMBER() OVER (PARTITION BY si.customer ORDER BY si.posting_date ASC, si.creation ASC) as rn
            FROM `tabSales Invoice` si
            WHERE si.docstatus = 1
            AND si.customer IN %(customers)s
            AND si.custom_outlet IN %(outlets)s
        ) t WHERE rn = 1
    """, {**values, "customers": customer_names}, as_dict=True)

    outlet_count = {}
    for r in rows:
        outlet_count[r.custom_outlet] = outlet_count.get(r.custom_outlet, 0) + 1
    return outlet_count


def get_chart(data):
    rows = [r for r in data if r.get("outlet") and r["outlet"] != "<b>TOTAL</b>"][:10]
    if not rows:
        return None
    return {
        "data": {
            "labels": [r["outlet"] for r in rows],
            "datasets": [{"name": _("Penjualan"), "values": [r["penjualan"] for r in rows]}],
        },
        "type": "bar",
        "title": _("Penjualan per Outlet"),
    }


def get_summary(data):
    if not data:
        return None
    total = data[-1]
    return [
        {"label": _("Customer Baru"), "value": total["customer_baru"], "indicator": "blue"},
        {"label": _("Member Aktif"), "value": total["member_aktif"], "indicator": "green"},
        {"label": _("Visitor"), "value": total["visitor"], "indicator": "orange"},
        {"label": _("Repeat Order"), "value": total["repeat_order"], "indicator": "purple"},
        {"label": _("Penjualan"), "value": total["penjualan"], "datatype": "Currency", "indicator": "green"},
    ]
