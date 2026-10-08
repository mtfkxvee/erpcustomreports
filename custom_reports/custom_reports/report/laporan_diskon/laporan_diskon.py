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
            children = frappe.db.get_all("Outlet", filters={"parent_outlet": current}, fields=["name", "is_group"])
            for c in children:
                queue.append(c["name"])
    return result if result else [outlet]


def get_outlet_list(filters):
    outlet_raw = filters.get("outlet")
    if not outlet_raw:
        return []
    if isinstance(outlet_raw, list):
        outlets = []
        for o in outlet_raw:
            if isinstance(o, dict):
                outlets.append(o.get("value") or o.get("name") or "")
            else:
                outlets.append(str(o))
        outlets = [o for o in outlets if o]
    else:
        outlets = [str(outlet_raw)]
    result = []
    for o in outlets:
        children = get_outlet_children(o)
        for c in children:
            if c not in result:
                result.append(c)
    return result


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
    data, chart, summary = get_data(filters)
    return columns, data, None, chart, summary


def get_columns():
    return [
        {"fieldname": "posting_date",   "label": _("Tanggal"),              "fieldtype": "Date",     "width": 110},
        {"fieldname": "diskon_manual",  "label": _("Diskon Manual (Rp)"),   "fieldtype": "Currency", "width": 160},
        {"fieldname": "diskon_promo",   "label": _("Diskon Promo (Rp)"),    "fieldtype": "Currency", "width": 160},
        {"fieldname": "diskon_rafaksi", "label": _("Diskon Rafaksi (Rp)"),  "fieldtype": "Currency", "width": 160},
        {"fieldname": "diskon_member",  "label": _("Diskon Member (Rp)"),   "fieldtype": "Currency", "width": 160},
        {"fieldname": "total_diskon",   "label": _("Total Diskon (Rp)"),    "fieldtype": "Currency", "width": 160},
    ]


def get_data(filters):
    outlet_list = get_outlet_list(filters)

    # Build outlet condition
    outlet_cond_si  = ""
    outlet_cond_gle = ""
    if outlet_list:
        out_str = "({})".format(", ".join(["'{}'".format(o.replace("'","''")) for o in outlet_list]))
        outlet_cond_si  = "AND si.custom_outlet IN {}".format(out_str)
        outlet_cond_gle = "AND si.custom_outlet IN {}".format(out_str)

    values = {
        "from_date": filters["from_date"],
        "to_date":   filters["to_date"],
    }

    # Kasir filter
    kasir_cond_si  = ""
    kasir_cond_gle = ""
    if filters.get("kasir"):
        kasir_cond_si  = "AND si.owner = %(kasir)s"
        kasir_cond_gle = "AND si.owner = %(kasir)s"
        values["kasir"] = filters["kasir"]

    # Query 1: Diskon Manual per tanggal (dari header Sales Invoice)
    sql_manual = (
        "SELECT gle.posting_date, SUM(gle.debit) - SUM(gle.credit) AS diskon_manual"
        " FROM `tabGL Entry` gle"
        " JOIN `tabSales Invoice` si ON si.name = gle.voucher_no"
        " WHERE gle.voucher_type = 'Sales Invoice'"
        " AND gle.is_cancelled = 0"
        " AND gle.account = 'Potongan Penjualan'"
        " AND gle.posting_date BETWEEN %(from_date)s AND %(to_date)s"
        " {outlet_cond} {kasir_cond}"
        " GROUP BY gle.posting_date"
    ).format(outlet_cond=outlet_cond_gle, kasir_cond=kasir_cond_gle)
    # Query 2: Diskon dari GL Entry per akun per tanggal
    sql_gle = (
        "SELECT gle.posting_date,"
        " SUM(CASE WHEN gle.account = 'Promo - X' THEN gle.debit ELSE 0 END) AS diskon_promo,"
        " SUM(CASE WHEN gle.account = 'RAFAKSI DISCOUNT - X' THEN gle.debit ELSE 0 END) AS diskon_rafaksi,"
        " SUM(CASE WHEN gle.account = 'MEMBER - X' THEN gle.debit ELSE 0 END) AS diskon_member"
        " FROM `tabGL Entry` gle"
        " JOIN `tabSales Invoice` si ON si.name = gle.voucher_no"
        " WHERE gle.voucher_type = 'Sales Invoice'"
        " AND gle.is_cancelled = 0"
        " AND gle.account IN ('Promo - X', 'RAFAKSI DISCOUNT - X', 'MEMBER - X')"
        " AND gle.posting_date BETWEEN %(from_date)s AND %(to_date)s"
        " {outlet_cond} {kasir_cond}"
        " GROUP BY gle.posting_date"
    ).format(outlet_cond=outlet_cond_gle, kasir_cond=kasir_cond_gle)

    manual_rows = frappe.db.sql(sql_manual, values, as_dict=True)
    gle_rows    = frappe.db.sql(sql_gle,    values, as_dict=True)

    # Build maps per tanggal
    manual_map = {str(r["posting_date"]): flt(r["diskon_manual"]) for r in manual_rows}
    gle_map    = {str(r["posting_date"]): r for r in gle_rows}

    # Gabungkan semua tanggal
    all_dates = sorted(set(list(manual_map.keys()) + list(gle_map.keys())))

    rows = []
    grand = {"manual": 0, "promo": 0, "rafaksi": 0, "member": 0, "total": 0}

    for d in all_dates:
        manual   = flt(manual_map.get(d, 0))
        gle      = gle_map.get(d, {})
        promo    = flt(gle.get("diskon_promo", 0))
        rafaksi  = flt(gle.get("diskon_rafaksi", 0))
        member   = flt(gle.get("diskon_member", 0))
        total    = manual + promo + rafaksi + member

        grand["manual"]  += manual
        grand["promo"]   += promo
        grand["rafaksi"] += rafaksi
        grand["member"]  += member
        grand["total"]   += total

        rows.append({
            "posting_date":   d,
            "diskon_manual":  manual,
            "diskon_promo":   promo,
            "diskon_rafaksi": rafaksi,
            "diskon_member":  member,
            "total_diskon":   total,
        })

    # Baris total
    if rows:
        rows.append({
            "posting_date":   None,
            "diskon_manual":  grand["manual"],
            "diskon_promo":   grand["promo"],
            "diskon_rafaksi": grand["rafaksi"],
            "diskon_member":  grand["member"],
            "total_diskon":   grand["total"],
        })

    # Chart
    chart_data = [r for r in rows if r.get("posting_date")]
    chart = None
    if chart_data:
        chart = {
            "data": {
                "labels": [str(r["posting_date"]) for r in chart_data],
                "datasets": [
                    {"name": "Diskon Manual",  "values": [r["diskon_manual"]  for r in chart_data], "chartType": "bar"},
                    {"name": "Diskon Promo",   "values": [r["diskon_promo"]   for r in chart_data], "chartType": "bar"},
                    {"name": "Diskon Rafaksi", "values": [r["diskon_rafaksi"] for r in chart_data], "chartType": "bar"},
                    {"name": "Diskon Member",  "values": [r["diskon_member"]  for r in chart_data], "chartType": "bar"},
                ]
            },
            "type": "bar",
            "fieldtype": "Currency",
            "colors": ["#5E64FF", "#FF9800", "#E91E63", "#4CAF50"],
            "axisOptions": {"xIsSeries": 1},
            "barOptions": {"stacked": 1},
            "height": 300,
        }

    # Summary
    summary = [
        {"value": grand["manual"],  "label": "Diskon Manual",  "datatype": "Currency", "indicator": "blue"},
        {"value": grand["promo"],   "label": "Diskon Promo",   "datatype": "Currency", "indicator": "orange"},
        {"value": grand["rafaksi"], "label": "Diskon Rafaksi", "datatype": "Currency", "indicator": "red"},
        {"value": grand["member"],  "label": "Diskon Member",  "datatype": "Currency", "indicator": "green"},
        {"value": grand["total"],   "label": "Total Diskon",   "datatype": "Currency", "indicator": "purple"},
    ]

    return rows, chart, summary
