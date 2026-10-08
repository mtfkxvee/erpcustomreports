import frappe
from frappe import _


@frappe.whitelist()
def get_platforms(doctype=None, txt=None, searchfield=None, start=0, page_len=20, filters=None):
    rows = frappe.db.sql(
        "SELECT DISTINCT platform FROM `tabMarketing Social Content` WHERE platform LIKE %(txt)s ORDER BY platform LIMIT %(page_len)s",
        {"txt": f"%{txt or ''}%", "page_len": page_len},
    )
    return [[r[0]] for r in rows]


@frappe.whitelist()
def get_accounts(doctype=None, txt=None, searchfield=None, start=0, page_len=20, filters=None):
    rows = frappe.db.sql(
        "SELECT DISTINCT account_name FROM `tabMarketing Social Content` WHERE account_name LIKE %(txt)s ORDER BY account_name LIMIT %(page_len)s",
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
        {"fieldname": "posting_date", "label": _("Tanggal"), "fieldtype": "Date", "width": 100},
        {"fieldname": "platform", "label": _("Platform"), "fieldtype": "Data", "width": 90},
        {"fieldname": "account_name", "label": _("Akun"), "fieldtype": "Data", "width": 150},
        {"fieldname": "content_type", "label": _("Tipe"), "fieldtype": "Data", "width": 80},
        {"fieldname": "caption", "label": _("Caption"), "fieldtype": "Data", "width": 250},
        {"fieldname": "url", "label": _("URL"), "fieldtype": "Data", "width": 200},
        {"fieldname": "likes", "label": _("Like"), "fieldtype": "Int", "width": 80},
        {"fieldname": "comments", "label": _("Komentar"), "fieldtype": "Int", "width": 90},
        {"fieldname": "shares", "label": _("Share"), "fieldtype": "Int", "width": 80},
        {"fieldname": "saved", "label": _("Saved"), "fieldtype": "Int", "width": 80},
        {"fieldname": "views", "label": _("Views"), "fieldtype": "Int", "width": 90},
        {"fieldname": "reach", "label": _("Reach"), "fieldtype": "Int", "width": 90},
        {"fieldname": "interactions", "label": _("Interaction"), "fieldtype": "Int", "width": 100},
    ]


def get_data(filters):
    conditions = ["1=1"]
    values = {}

    if filters.get("from_date"):
        conditions.append("posting_date >= %(from_date)s")
        values["from_date"] = filters["from_date"]
    if filters.get("to_date"):
        conditions.append("posting_date <= %(to_date)s")
        values["to_date"] = filters["to_date"]

    platform = filters.get("platform")
    if platform:
        values["platform"] = platform if isinstance(platform, list) else [platform]
        conditions.append("platform IN %(platform)s")

    account_name = filters.get("account_name")
    if account_name:
        values["account_name"] = account_name if isinstance(account_name, list) else [account_name]
        conditions.append("account_name IN %(account_name)s")

    rows = frappe.db.sql(f"""
        SELECT posting_date, platform, account_name, content_type, caption, url,
               likes, comments, shares, saved, views, reach, interactions
        FROM `tabMarketing Social Content`
        WHERE {' AND '.join(conditions)}
        ORDER BY posting_date DESC, views DESC
    """, values, as_dict=True)

    return rows


def get_chart(data):
    if not data:
        return None
    top = sorted(data, key=lambda r: r.get("views") or 0, reverse=True)[:10]
    labels = [(r.get("account_name") or "") + " - " + (r.get("posting_date").strftime("%d/%m") if r.get("posting_date") else "") for r in top]
    return {
        "data": {
            "labels": labels,
            "datasets": [{"name": _("Views"), "values": [r.get("views") or 0 for r in top]}],
        },
        "type": "bar",
        "title": _("Top 10 Konten berdasarkan Views"),
    }


def get_summary(data):
    if not data:
        return None
    total_konten = len(data)
    total_views = sum(r.get("views") or 0 for r in data)
    total_likes = sum(r.get("likes") or 0 for r in data)
    total_comments = sum(r.get("comments") or 0 for r in data)
    total_shares = sum(r.get("shares") or 0 for r in data)
    total_interactions = sum(r.get("interactions") or 0 for r in data)

    return [
        {"label": _("Total Konten"), "value": total_konten, "indicator": "blue"},
        {"label": _("Total Views"), "value": total_views, "indicator": "green"},
        {"label": _("Total Likes"), "value": total_likes, "indicator": "pink"},
        {"label": _("Total Komentar"), "value": total_comments, "indicator": "orange"},
        {"label": _("Total Share"), "value": total_shares, "indicator": "purple"},
        {"label": _("Total Interaksi"), "value": total_interactions, "indicator": "green"},
    ]
