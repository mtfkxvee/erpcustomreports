import frappe
from frappe import _
from frappe.utils import today, date_diff


def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {"label": _("Supplier"), "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 200},
        {"label": _("No. Invoice"), "fieldname": "name", "fieldtype": "Link", "options": "Purchase Invoice", "width": 160},
        {"label": _("Tgl Invoice"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
        {"label": _("Jatuh Tempo"), "fieldname": "due_date", "fieldtype": "Date", "width": 100},
        {"label": _("Nilai Invoice"), "fieldname": "grand_total", "fieldtype": "Currency", "width": 150},
        {"label": _("Terbayar"), "fieldname": "paid_amount", "fieldtype": "Currency", "width": 150},
        {"label": _("Sisa Hutang"), "fieldname": "outstanding_amount", "fieldtype": "Currency", "width": 150},
        {"label": _("Umur (Hari)"), "fieldname": "age_days", "fieldtype": "Int", "width": 100},
        {"label": _("0-30 Hari"), "fieldname": "bucket_0_30", "fieldtype": "Currency", "width": 130},
        {"label": _("31-60 Hari"), "fieldname": "bucket_31_60", "fieldtype": "Currency", "width": 130},
        {"label": _("61-90 Hari"), "fieldname": "bucket_61_90", "fieldtype": "Currency", "width": 130},
        {"label": _("  >90 Hari"), "fieldname": "bucket_90", "fieldtype": "Currency", "width": 130},
    ]


def get_data(filters):
    conditions = "pi.docstatus = 1 AND pi.outstanding_amount > 0"

    if filters.get("company"):
        conditions += " AND pi.company = %(company)s"
    if filters.get("supplier"):
        conditions += " AND pi.supplier = %(supplier)s"
    if filters.get("from_date"):
        conditions += " AND pi.posting_date >= %(from_date)s"
    if filters.get("to_date"):
        conditions += " AND pi.posting_date <= %(to_date)s"
    if filters.get("due_from"):
        conditions += " AND pi.due_date >= %(due_from)s"
    if filters.get("due_to"):
        conditions += " AND pi.due_date <= %(due_to)s"

    invoices = frappe.db.sql(
        f"""
        SELECT
            pi.supplier,
            pi.name,
            pi.posting_date,
            pi.due_date,
            pi.grand_total,
            (pi.grand_total - pi.outstanding_amount) AS paid_amount,
            pi.outstanding_amount
        FROM `tabPurchase Invoice` pi
        WHERE {conditions}
        ORDER BY pi.supplier, pi.posting_date
        """,
        filters,
        as_dict=True,
    )

    as_of = today()
    data = []
    current_supplier = None
    supplier_totals = {}

    for inv in invoices:
        age = date_diff(as_of, inv.due_date)
        if age < 0:
            age = 0

        inv.age_days = age
        outstanding = inv.outstanding_amount or 0

        inv.bucket_0_30 = outstanding if age <= 30 else 0
        inv.bucket_31_60 = outstanding if 31 <= age <= 60 else 0
        inv.bucket_61_90 = outstanding if 61 <= age <= 90 else 0
        inv.bucket_90 = outstanding if age > 90 else 0

        # Group header per supplier
        if inv.supplier != current_supplier:
            if current_supplier and current_supplier in supplier_totals:
                data.append(supplier_totals[current_supplier])
            current_supplier = inv.supplier
            supplier_totals[current_supplier] = {
                "supplier": f"<b>{inv.supplier}</b>",
                "name": "", "posting_date": "", "due_date": "",
                "grand_total": 0, "paid_amount": 0, "outstanding_amount": 0,
                "age_days": "", "bucket_0_30": 0, "bucket_31_60": 0,
                "bucket_61_90": 0, "bucket_90": 0,
                "bold": 1, "is_group": True,
            }

        # Akumulasi total supplier
        t = supplier_totals[current_supplier]
        t["grand_total"] += inv.grand_total or 0
        t["paid_amount"] += inv.paid_amount or 0
        t["outstanding_amount"] += outstanding
        t["bucket_0_30"] += inv.bucket_0_30
        t["bucket_31_60"] += inv.bucket_31_60
        t["bucket_61_90"] += inv.bucket_61_90
        t["bucket_90"] += inv.bucket_90

        data.append(inv)

    # Append total supplier terakhir
    if current_supplier and current_supplier in supplier_totals:
        data.append(supplier_totals[current_supplier])

    return data
