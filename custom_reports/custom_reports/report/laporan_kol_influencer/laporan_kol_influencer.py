import frappe
from frappe import _
from frappe.utils import flt


@frappe.whitelist()
def get_platforms(doctype=None, txt=None, searchfield=None, start=0, page_len=20, filters=None):
    rows = frappe.db.sql(
        "SELECT DISTINCT platform FROM `tabMarketing KOL Activity` WHERE platform LIKE %(txt)s ORDER BY platform LIMIT %(page_len)s",
        {"txt": f"%{txt or ''}%", "page_len": page_len},
    )
    return [[r[0]] for r in rows]


def execute(filters=None):
    filters = filters or {}

    columns = get_columns()
    data = get_data(filters)
    chart = get_chart(data)
    summary = get_summary(data)

    return columns, data, None, chart, summary


def get_columns():
    return [
        {"fieldname": "kol", "label": _("KOL / Influencer"), "fieldtype": "Link", "options": "Marketing KOL", "width": 180},
        {"fieldname": "platform", "label": _("Platform"), "fieldtype": "Data", "width": 100},
        {"fieldname": "jumlah_postingan", "label": _("Jumlah Postingan"), "fieldtype": "Int", "width": 130},
        {"fieldname": "pengeluaran", "label": _("Pengeluaran (Rp)"), "fieldtype": "Currency", "width": 150},
        {"fieldname": "views", "label": _("Views"), "fieldtype": "Int", "width": 90},
        {"fieldname": "likes", "label": _("Like"), "fieldtype": "Int", "width": 80},
        {"fieldname": "comments", "label": _("Komentar"), "fieldtype": "Int", "width": 90},
        {"fieldname": "shares", "label": _("Share"), "fieldtype": "Int", "width": 80},
        {"fieldname": "interactions", "label": _("Interaction"), "fieldtype": "Int", "width": 100},
        {"fieldname": "cost_per_view", "label": _("Cost per View (Rp)"), "fieldtype": "Currency", "width": 140},
    ]


def get_data(filters):
    conditions = ["1=1"]
    values = {}

    if filters.get("from_date"):
        conditions.append("a.posting_date >= %(from_date)s")
        values["from_date"] = filters["from_date"]
    if filters.get("to_date"):
        conditions.append("a.posting_date <= %(to_date)s")
        values["to_date"] = filters["to_date"]

    kol = filters.get("kol")
    if kol:
        values["kol"] = kol if isinstance(kol, list) else [kol]
        conditions.append("a.kol IN %(kol)s")

    platform = filters.get("platform")
    if platform:
        values["platform"] = platform if isinstance(platform, list) else [platform]
        conditions.append("a.platform IN %(platform)s")

    rows = frappe.db.sql(f"""
        SELECT a.kol as kol, a.platform as platform,
               COUNT(*) as jumlah_postingan,
               SUM(a.cost) as pengeluaran,
               SUM(a.views) as views,
               SUM(a.likes) as likes,
               SUM(a.comments) as comments,
               SUM(a.shares) as shares,
               SUM(a.interactions) as interactions
        FROM `tabMarketing KOL Activity` a
        WHERE {' AND '.join(conditions)}
        GROUP BY a.kol, a.platform
        ORDER BY pengeluaran DESC
    """, values, as_dict=True)

    data = []
    grand = {"jumlah_postingan": 0, "pengeluaran": 0, "views": 0, "likes": 0, "comments": 0, "shares": 0, "interactions": 0}

    for r in rows:
        views = int(r.views or 0)
        pengeluaran = flt(r.pengeluaran)
        cost_per_view = (pengeluaran / views) if views else 0
        row = {
            "kol": r.kol,
            "platform": r.platform,
            "jumlah_postingan": int(r.jumlah_postingan),
            "pengeluaran": pengeluaran,
            "views": views,
            "likes": int(r.likes or 0),
            "comments": int(r.comments or 0),
            "shares": int(r.shares or 0),
            "interactions": int(r.interactions or 0),
            "cost_per_view": cost_per_view,
        }
        data.append(row)
        for k in grand:
            grand[k] += row[k]

    if data:
        data.append({
            "kol": "<b>TOTAL</b>",
            "platform": "",
            "jumlah_postingan": grand["jumlah_postingan"],
            "pengeluaran": grand["pengeluaran"],
            "views": grand["views"],
            "likes": grand["likes"],
            "comments": grand["comments"],
            "shares": grand["shares"],
            "interactions": grand["interactions"],
            "cost_per_view": (grand["pengeluaran"] / grand["views"]) if grand["views"] else 0,
        })

    return data


def get_chart(data):
    rows = [r for r in data if r.get("kol") and r["kol"] != "<b>TOTAL</b>"][:10]
    if not rows:
        return None
    return {
        "data": {
            "labels": [r["kol"] for r in rows],
            "datasets": [{"name": _("Pengeluaran"), "values": [r["pengeluaran"] for r in rows]}],
        },
        "type": "bar",
        "title": _("Pengeluaran per KOL"),
    }


def get_summary(data):
    if not data:
        return None
    total = data[-1]
    jumlah_kol = len({r["kol"] for r in data[:-1]})
    return [
        {"label": _("Jumlah KOL"), "value": jumlah_kol, "indicator": "blue"},
        {"label": _("Jumlah Postingan"), "value": total["jumlah_postingan"], "indicator": "orange"},
        {"label": _("Total Pengeluaran"), "value": total["pengeluaran"], "datatype": "Currency", "indicator": "red"},
        {"label": _("Total Views"), "value": total["views"], "indicator": "green"},
        {"label": _("Total Interaksi"), "value": total["interactions"], "indicator": "purple"},
    ]
