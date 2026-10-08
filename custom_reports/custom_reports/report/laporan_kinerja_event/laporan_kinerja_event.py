import calendar

import frappe
from frappe import _
from frappe.utils import add_days, getdate
from dateutil.relativedelta import relativedelta


def execute(filters=None):
    filters = filters or {}
    event_name = filters.get("marketing_event")

    if not event_name:
        frappe.msgprint(_("Pilih Marketing Event dulu."), indicator="orange", alert=True)
        return [], []

    event = frappe.get_doc("Marketing Event", event_name)
    from_date = getdate(event.from_date)
    to_date = getdate(event.to_date)
    outlets = [row.outlet for row in event.outlets]

    if not outlets:
        frappe.msgprint(_("Event ini belum punya outlet."), indicator="orange", alert=True)
        return [], []

    event_dates = date_range_list(from_date, to_date)
    prev_month_dates = [get_same_weekday_prev_month(d) for d in event_dates]
    prev_year_dates = [d - relativedelta(years=1) for d in event_dates]

    outlet_group = get_outlet_group_map(outlets)

    columns = get_columns()
    data = get_data(outlets, outlet_group, event_dates, prev_month_dates, prev_year_dates)
    chart = get_chart(data)
    report_summary = get_summary(event, event_dates)

    return columns, data, None, chart, report_summary


def date_range_list(from_date, to_date):
    dates = []
    d = from_date
    while d <= to_date:
        dates.append(d)
        d = add_days(d, 1)
    return dates


def get_same_weekday_prev_month(d):
    weekday = d.weekday()
    occurrence = (d.day - 1) // 7
    prev_month_first = d.replace(day=1) - relativedelta(months=1)
    _, days_in_month = calendar.monthrange(prev_month_first.year, prev_month_first.month)
    matches = [
        prev_month_first.replace(day=day)
        for day in range(1, days_in_month + 1)
        if prev_month_first.replace(day=day).weekday() == weekday
    ]
    if occurrence < len(matches):
        return matches[occurrence]
    return matches[-1]


def get_outlet_group_map(outlets):
    rows = frappe.get_all("Outlet", filters={"name": ["in", outlets]}, fields=["name", "parent_outlet"])
    group_map = {}
    for r in rows:
        parent = (r.parent_outlet or "").upper()
        if parent == "FASHION":
            group_map[r.name] = "Fashion"
        elif parent == "FMCG":
            group_map[r.name] = "FMCG"
        else:
            group_map[r.name] = "Lainnya"
    return group_map


def get_columns():
    return [
        {"fieldname": "metric", "label": _("Metrik"), "fieldtype": "Data", "width": 180},
        {"fieldname": "fmcg", "label": _("FMCG (Event)"), "fieldtype": "Float", "width": 130},
        {"fieldname": "fashion", "label": _("Fashion (Event)"), "fieldtype": "Float", "width": 130},
        {"fieldname": "total_event", "label": _("Total (Event)"), "fieldtype": "Float", "width": 130},
        {"fieldname": "total_prev_month", "label": _("Total (Periode Sama, Bulan Lalu)"), "fieldtype": "Float", "width": 190},
        {"fieldname": "total_prev_year", "label": _("Total (Periode Sama, Tahun Lalu)"), "fieldtype": "Float", "width": 190},
    ]


def get_visitor_count(outlets, dates):
    if not dates:
        return 0
    row = frappe.db.sql("""
        SELECT SUM(pcs.visitor) as total
        FROM `tabPOS Closing Shift` pcs
        JOIN `tabPOS Profile` pp ON pp.name = pcs.pos_profile
        WHERE pp.custom_outlet IN %(outlets)s
        AND pcs.posting_date IN %(dates)s
        AND pcs.docstatus = 1
    """, {"outlets": outlets, "dates": dates}, as_dict=True)
    return flt(row[0].total) if row else 0


def get_sales_metrics(outlets, dates):
    if not dates:
        return 0, 0
    row = frappe.db.sql("""
        SELECT COUNT(*) as txn_count, SUM(grand_total) as total_sales
        FROM `tabSales Invoice`
        WHERE custom_outlet IN %(outlets)s
        AND posting_date IN %(dates)s
        AND docstatus = 1
    """, {"outlets": outlets, "dates": dates}, as_dict=True)
    if not row:
        return 0, 0
    return int(row[0].txn_count or 0), flt(row[0].total_sales)


def flt(v):
    return frappe.utils.flt(v)


def get_data(outlets, outlet_group, event_dates, prev_month_dates, prev_year_dates):
    fmcg_outlets = [o for o in outlets if outlet_group.get(o) == "FMCG"]
    fashion_outlets = [o for o in outlets if outlet_group.get(o) == "Fashion"]

    visitor_fmcg = get_visitor_count(fmcg_outlets, event_dates) if fmcg_outlets else 0
    visitor_fashion = get_visitor_count(fashion_outlets, event_dates) if fashion_outlets else 0
    visitor_total_event = get_visitor_count(outlets, event_dates)
    visitor_total_prev_month = get_visitor_count(outlets, prev_month_dates)
    visitor_total_prev_year = get_visitor_count(outlets, prev_year_dates)

    txn_fmcg, sales_fmcg = get_sales_metrics(fmcg_outlets, event_dates) if fmcg_outlets else (0, 0)
    txn_fashion, sales_fashion = get_sales_metrics(fashion_outlets, event_dates) if fashion_outlets else (0, 0)
    txn_total_event, sales_total_event = get_sales_metrics(outlets, event_dates)
    txn_total_prev_month, sales_total_prev_month = get_sales_metrics(outlets, prev_month_dates)
    txn_total_prev_year, sales_total_prev_year = get_sales_metrics(outlets, prev_year_dates)

    return [
        {
            "metric": _("Visitor"),
            "fmcg": visitor_fmcg,
            "fashion": visitor_fashion,
            "total_event": visitor_total_event,
            "total_prev_month": visitor_total_prev_month,
            "total_prev_year": visitor_total_prev_year,
        },
        {
            "metric": _("Jumlah Transaksi"),
            "fmcg": txn_fmcg,
            "fashion": txn_fashion,
            "total_event": txn_total_event,
            "total_prev_month": txn_total_prev_month,
            "total_prev_year": txn_total_prev_year,
        },
        {
            "metric": _("Penjualan (Rp)"),
            "fmcg": sales_fmcg,
            "fashion": sales_fashion,
            "total_event": sales_total_event,
            "total_prev_month": sales_total_prev_month,
            "total_prev_year": sales_total_prev_year,
        },
    ]


def get_chart(data):
    sales_row = next((r for r in data if r["metric"] == _("Penjualan (Rp)")), None)
    if not sales_row:
        return None
    return {
        "data": {
            "labels": [_("Event"), _("Bulan Lalu"), _("Tahun Lalu")],
            "datasets": [{
                "name": _("Penjualan"),
                "values": [sales_row["total_event"], sales_row["total_prev_month"], sales_row["total_prev_year"]],
            }],
        },
        "type": "bar",
        "title": _("Perbandingan Penjualan"),
    }


def get_summary(event, event_dates):
    return [
        {"label": _("Event"), "value": event.title, "indicator": "blue"},
        {"label": _("Jumlah Hari"), "value": len(event_dates), "indicator": "green"},
        {"label": _("Jumlah Outlet"), "value": len(event.outlets), "indicator": "orange"},
    ]
