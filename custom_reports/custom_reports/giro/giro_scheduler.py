import frappe
from frappe.utils import today

GIRO_BELUM_CAIR_ACCOUNT = "GIRO BELUM CAIR - X"


def process_cheque_clearance():
    pending_cheques = frappe.db.sql(
        """
        SELECT pe.name, pe.company, pe.party, pe.paid_amount,
               pe.reference_no, pe.reference_date,
               pe.cheque_bank_account
        FROM `tabPayment Entry` pe
        WHERE pe.docstatus = 1
          AND pe.cheque_status = 'Pending'
          AND pe.is_cheque_payment = 1
          AND pe.reference_date <= %s
          AND pe.payment_type = 'Pay'
        """,
        (today(),),
        as_dict=True,
    )
    if not pending_cheques:
        return
    for pe in pending_cheques:
        try:
            _create_clearing_je(pe)
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"Giro Clearing Failed: {pe.name}")


def _create_clearing_je(pe):
    bank_account = pe.cheque_bank_account
    if not bank_account:
        frappe.log_error(f"No cheque_bank_account for PE {pe.name}", "Giro Clearing")
        return

    je = frappe.new_doc("Journal Entry")
    je.voucher_type = "Journal Entry"
    je.company = pe.company
    je.posting_date = today()
    je.cheque_no = pe.reference_no
    je.cheque_date = pe.reference_date
    je.user_remark = f"Giro clearing - {pe.name} - {pe.party} - Ref: {pe.reference_no}"
    je.append("accounts", {
        "account": GIRO_BELUM_CAIR_ACCOUNT,
        "debit_in_account_currency": pe.paid_amount,
        "credit_in_account_currency": 0,
    })
    je.append("accounts", {
        "account": bank_account,
        "debit_in_account_currency": 0,
        "credit_in_account_currency": pe.paid_amount,
    })
    je.insert(ignore_permissions=True)
    je.submit()
    frappe.db.set_value("Payment Entry", pe.name, {
        "cheque_status": "Cleared",
        "cheque_clearing_je": je.name,
    })
    frappe.db.commit()
