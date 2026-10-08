import frappe
from frappe import _
from frappe.utils import flt

DAY_MAP = {0: "Senin", 1: "Selasa", 2: "Rabu", 3: "Kamis", 4: "Jumat", 5: "Sabtu", 6: "Minggu"}


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


def build_outlet_where(outlet_list, alias="si"):
    if not outlet_list:
        return ""
    if len(outlet_list) == 1:
        return "AND {}.custom_outlet = '{}'".format(alias, outlet_list[0].replace("'", "''"))
    out_str = "({})".format(", ".join(["'{}'".format(o.replace("'","''")) for o in outlet_list]))
    return "AND {}.custom_outlet IN {}".format(alias, out_str)


def get_target_map(filters, outlet_list):
    conditions = ["DATE(std.tanggal) BETWEEN %(from_date)s AND %(to_date)s"]
    values = {"from_date": filters["from_date"], "to_date": filters["to_date"]}
    if outlet_list:
        out_str = "({})".format(", ".join(["'{}'".format(o.replace("'","''")) for o in outlet_list]))
        conditions.append("std.parent IN {}".format(out_str))
    sql = (
        "SELECT std.tanggal, SUM(std.target_harian) AS target"
        " FROM `tabSales Target Daily` std"
        " WHERE " + " AND ".join(conditions) +
        " GROUP BY std.tanggal"
    )
    rows = frappe.db.sql(sql, values, as_dict=True)
    return {str(r["tanggal"]): flt(r["target"]) for r in rows}


def get_visitor_map(filters, outlet_list):
    conditions = [
        "pcs.docstatus = 1",
        "DATE(pcs.period_start_date) BETWEEN %(from_date)s AND %(to_date)s",
    ]
    values = {"from_date": filters["from_date"], "to_date": filters["to_date"]}
    if outlet_list:
        out_str = "({})".format(", ".join(["'{}'".format(o.replace("'","''")) for o in outlet_list]))
        conditions.append("pp.custom_outlet IN {}".format(out_str))
    sql = (
        "SELECT DATE(pcs.period_start_date) AS tgl, SUM(pcs.visitor) AS total_visitor"
        " FROM `tabPOS Closing Shift` pcs"
        " JOIN `tabPOS Profile` pp ON pp.name = pcs.pos_profile"
        " WHERE " + " AND ".join(conditions) +
        " GROUP BY DATE(pcs.period_start_date)"
    )
    rows = frappe.db.sql(sql, values, as_dict=True)
    return {str(r["tgl"]): int(r["total_visitor"] or 0) for r in rows}


def execute(filters=None):
    if not filters:
        filters = {}
    if not filters.get("from_date") or not filters.get("to_date"):
        frappe.msgprint(
            "Silakan pilih <b>Dari Tanggal</b> dan <b>Sampai Tanggal</b> terlebih dahulu.",
            indicator="orange", alert=True
        )
        return [], []
    mode = filters.get("mode") or "Harian"
    columns = get_columns(mode)
    data    = get_data(filters, mode)
    chart   = get_chart(data, mode)
    summary = get_summary(data)
    return columns, data, None, chart, summary


def get_columns(mode):
    if mode == "Per Hari":
        first = {"fieldname": "hari", "label": _("Hari"), "fieldtype": "Data", "width": 110}
    else:
        first = {"fieldname": "posting_date", "label": _("Tanggal"), "fieldtype": "Date", "width": 110}
    return [
        first,
        {"fieldname": "target",          "label": _("Target (Rp)"),      "fieldtype": "Currency", "width": 150},
        {"fieldname": "sales",           "label": _("Sales (Rp)"),       "fieldtype": "Currency", "width": 160},
        {"fieldname": "achievement",     "label": _("Pencapaian (%)"),    "fieldtype": "Percent",  "width": 130},
        {"fieldname": "total_transaksi", "label": _("Total Transaksi"),   "fieldtype": "Int",      "width": 130},
        {"fieldname": "atv",             "label": _("ATV (Rp)"),         "fieldtype": "Currency", "width": 140},
        {"fieldname": "total_item",      "label": _("Item Terjual"),     "fieldtype": "Int",      "width": 120},
        {"fieldname": "total_qty",       "label": _("Qty Item Terjual"), "fieldtype": "Float",    "width": 130},
        {"fieldname": "visitor",         "label": _("Visitor"),          "fieldtype": "Int",      "width": 90},
        {"fieldname": "conv_rate",       "label": _("Conv. Rate (%)"),   "fieldtype": "Percent",  "width": 120},
    ]


def build_where(filters):
    outlet_list = get_outlet_list(filters)
    outlet_cond = build_outlet_where(outlet_list, "si")
    conditions = [
        "si.docstatus = 1",
        "si.is_return = 0",
        "si.posting_date BETWEEN %(from_date)s AND %(to_date)s",
    ]
    if outlet_cond:
        conditions.append(outlet_cond.lstrip("AND "))
    values = {"from_date": filters["from_date"], "to_date": filters["to_date"]}
    return "WHERE " + " AND ".join(conditions), values, outlet_list


def get_data(filters, mode):
    where, values, outlet_list = build_where(filters)
    target_map  = get_target_map(filters, outlet_list)
    visitor_map = get_visitor_map(filters, outlet_list)

    sql_main = (
        "SELECT si.posting_date,"
        " SUM(si.grand_total - COALESCE(si.loyalty_amount, 0)) AS sales,"
        " COUNT(si.name) AS total_transaksi"
        " FROM `tabSales Invoice` si"
        " {where}"
        " GROUP BY si.posting_date"
        " ORDER BY si.posting_date ASC"
    ).format(where=where)

    sql_item = (
        "SELECT si.posting_date,"
        " COUNT(DISTINCT sii.item_code) AS total_item,"
        " SUM(sii.qty) AS total_qty"
        " FROM `tabSales Invoice Item` sii"
        " JOIN `tabSales Invoice` si ON si.name = sii.parent"
        " {where}"
        " GROUP BY si.posting_date"
    ).format(where=where)

    main_rows = frappe.db.sql(sql_main, values, as_dict=True)
    item_rows  = frappe.db.sql(sql_item,  values, as_dict=True)

    item_map = {}
    for r in item_rows:
        item_map[str(r["posting_date"])] = {
            "total_item": int(r["total_item"] or 0),
            "total_qty":  flt(r["total_qty"] or 0),
        }

    if mode == "Per Hari":
        # Aggregate per weekday
        from datetime import date, timedelta
        weekday_data = {i: {"sales": 0, "total_transaksi": 0, "total_item": 0, "total_qty": 0, "target": 0} for i in range(7)}

        for r in main_rows:
            k  = str(r["posting_date"])
            wd = r["posting_date"].weekday()
            im = item_map.get(k, {})
            weekday_data[wd]["sales"]           += flt(r["sales"])
            weekday_data[wd]["total_transaksi"] += int(r["total_transaksi"])
            weekday_data[wd]["total_item"]      += im.get("total_item", 0)
            weekday_data[wd]["total_qty"]       += im.get("total_qty", 0)

        # Target per weekday — sum target harian per hari-dalam-minggu
        d = date.fromisoformat(str(filters["from_date"]))
        d_end = date.fromisoformat(str(filters["to_date"]))
        while d <= d_end:
            t = target_map.get(str(d), 0)
            weekday_data[d.weekday()]["target"] += t
            d += timedelta(days=1)

        rows = []
        grand_sales = grand_trx = grand_item = grand_qty = grand_target = 0

        for i in range(7):
            d2 = weekday_data[i]
            sales           = d2["sales"]
            total_transaksi = d2["total_transaksi"]
            total_item      = d2["total_item"]
            total_qty       = d2["total_qty"]
            target          = d2["target"]
            atv         = sales / total_transaksi if total_transaksi > 0 else 0
            achievement = (sales / target * 100) if target > 0 else 0
            grand_sales  += sales; grand_trx += total_transaksi
            grand_item   += total_item; grand_qty += total_qty; grand_target += target
            rows.append({
                "hari": DAY_MAP[i], "posting_date": None,
                "target": target, "sales": sales, "achievement": achievement,
                "total_transaksi": total_transaksi, "atv": atv,
                "total_item": total_item, "total_qty": total_qty,
                "visitor": 0, "conv_rate": 0,
            })

        if rows:
            grand_atv = grand_sales / grand_trx if grand_trx > 0 else 0
            grand_ach = (grand_sales / grand_target * 100) if grand_target > 0 else 0
            rows.append({
                "hari": "<b>TOTAL</b>", "posting_date": None,
                "target": grand_target, "sales": grand_sales, "achievement": grand_ach,
                "total_transaksi": grand_trx, "atv": grand_atv,
                "total_item": grand_item, "total_qty": grand_qty,
                "visitor": 0, "conv_rate": 0,
            })

    else:
        rows = []
        grand_sales = grand_trx = grand_item = grand_qty = grand_target = grand_visitor = 0

        for r in main_rows:
            k               = str(r["posting_date"])
            im              = item_map.get(k, {})
            sales           = flt(r["sales"])
            total_transaksi = int(r["total_transaksi"])
            total_item      = im.get("total_item", 0)
            total_qty       = im.get("total_qty", 0)
            target          = target_map.get(k, 0)
            visitor         = visitor_map.get(k, 0)
            atv         = sales / total_transaksi if total_transaksi > 0 else 0
            achievement = (sales / target * 100) if target > 0 else 0
            conv_rate   = (total_transaksi / visitor * 100) if visitor > 0 else 0

            grand_sales    += sales;  grand_trx     += total_transaksi
            grand_item     += total_item; grand_qty += total_qty
            grand_target   += target; grand_visitor += visitor

            rows.append({
                "posting_date": r["posting_date"], "hari": None,
                "target": target, "sales": sales, "achievement": achievement,
                "total_transaksi": total_transaksi, "atv": atv,
                "total_item": total_item, "total_qty": total_qty,
                "visitor": visitor, "conv_rate": conv_rate,
            })

        if rows:
            grand_atv  = grand_sales / grand_trx if grand_trx > 0 else 0
            grand_ach  = (grand_sales / grand_target * 100) if grand_target > 0 else 0
            grand_conv = (grand_trx / grand_visitor * 100) if grand_visitor > 0 else 0
            rows.append({
                "posting_date": None, "hari": None,
                "target": grand_target, "sales": grand_sales, "achievement": grand_ach,
                "total_transaksi": grand_trx, "atv": grand_atv,
                "total_item": grand_item, "total_qty": grand_qty,
                "visitor": grand_visitor, "conv_rate": grand_conv,
            })

    return rows


def get_chart(data, mode):
    if not data or len(data) <= 1:
        return None
    if mode == "Per Hari":
        chart_data = [r for r in data if r.get("hari") and r.get("hari") != "<b>TOTAL</b>"]
        labels = [r.get("hari", "") for r in chart_data]
    else:
        chart_data = [r for r in data if r.get("posting_date")]
        labels = [str(r.get("posting_date", "")) for r in chart_data]
    sales_vals  = [flt(r["sales"]) for r in chart_data]
    target_vals = [flt(r.get("target", 0)) for r in chart_data]
    trx_vals    = [int(r["total_transaksi"]) for r in chart_data]
    return {
        "data": {
            "labels": labels,
            "datasets": [
                {"name": "Target (Rp)", "values": target_vals, "chartType": "line"},
                {"name": "Sales (Rp)",  "values": sales_vals,  "chartType": "bar"},
                {"name": "Transaksi",   "values": trx_vals,    "chartType": "line"},
            ]
        },
        "type": "axis-mixed",
        "fieldtype": "Currency",
        "colors": ["#ff9800", "#5E64FF", "#FF5E5E"],
        "axisOptions": {"xIsSeries": 1},
        "height": 300,
    }


def get_summary(data):
    if not data:
        return None
    total = data[-1]
    return [
        {"value": total.get("target", 0),       "label": "Total Target",    "datatype": "Currency", "indicator": "orange"},
        {"value": total["sales"],               "label": "Total Sales",     "datatype": "Currency", "indicator": "green"},
        {"value": total.get("achievement", 0),  "label": "Pencapaian (%)",  "datatype": "Percent",  "indicator": "blue"},
        {"value": total["total_transaksi"],      "label": "Total Transaksi", "datatype": "Int",      "indicator": "blue"},
        {"value": total["atv"],                 "label": "ATV",             "datatype": "Currency", "indicator": "purple"},
        {"value": total.get("visitor", 0),      "label": "Total Visitor",   "datatype": "Int",      "indicator": "red"},
        {"value": total.get("conv_rate", 0),    "label": "Conv. Rate (%)",  "datatype": "Percent",  "indicator": "yellow"},
    ]
