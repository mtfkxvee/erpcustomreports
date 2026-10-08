import frappe
from frappe import _


def execute(filters=None):
    filters = filters or {}
    return get_columns(), get_data(filters)


def get_columns():
    return [
        {"label": _("Payment Entry"), "fieldname": "name", "fieldtype": "Link", "options": "Payment Entry", "width": 160},
        {"label": _("Tanggal"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
        {"label": _("Supplier"), "fieldname": "party", "fieldtype": "Link", "options": "Supplier", "width": 200},
        {"label": _("No. Referensi / Cek"), "fieldname": "reference_no", "fieldtype": "Data", "width": 160},
        {"label": _("Tgl Jatuh Tempo"), "fieldname": "reference_date", "fieldtype": "Date", "width": 120},
        {"label": _("Nominal"), "fieldname": "paid_amount", "fieldtype": "Currency", "width": 150},
        {"label": _("Status"), "fieldname": "cheque_status", "fieldtype": "Data", "width": 100},
        {"label": _("Clearing JE"), "fieldname": "cheque_clearing_je", "fieldtype": "Link", "options": "Journal Entry", "width": 160},
    ]


def get_data(filters):
    conditions = "pe.is_cheque_payment = 1 AND pe.docstatus = 1"
    if filters.get("company"):
        conditions += " AND pe.company = %(company)s"
    if filters.get("status"):
        conditions += " AND pe.cheque_status = %(status)s"
    if filters.get("from_date"):
        conditions += " AND pe.reference_date >= %(from_date)s"
    if filters.get("to_date"):
        conditions += " AND pe.reference_date <= %(to_date)s"
    return frappe.db.sql(
        f"""
        SELECT pe.name, pe.posting_date, pe.party, pe.reference_no,
               pe.reference_date, pe.paid_amount, pe.cheque_status, pe.cheque_clearing_je
        FROM `tabPayment Entry` pe
        WHERE {conditions}
        ORDER BY pe.reference_date ASC
        """,
        filters,
        as_dict=True,
    )
