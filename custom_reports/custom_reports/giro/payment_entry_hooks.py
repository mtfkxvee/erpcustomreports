import frappe

CHEQUE_MODES = {"cheque", "giro"}
GIRO_BELUM_CAIR_ACCOUNT = "GIRO BELUM CAIR - X"


def validate(doc, method):
    if doc.payment_type != "Pay":
        return
    mop = (doc.mode_of_payment or "").strip().lower()
    if mop not in CHEQUE_MODES:
        return
    # Simpan akun bank asli sebelum di-override
    if doc.paid_from and doc.paid_from != GIRO_BELUM_CAIR_ACCOUNT:
        doc.original_bank_account = doc.paid_from
    doc.paid_from = GIRO_BELUM_CAIR_ACCOUNT
    doc.paid_from_account_currency = "IDR"


def on_submit(doc, method):
    if doc.payment_type != "Pay":
        return
    mop = (doc.mode_of_payment or "").strip().lower()
    if mop not in CHEQUE_MODES:
        return
    frappe.db.set_value("Payment Entry", doc.name, {
        "is_cheque_payment": 1,
        "cheque_status": "Pending",
    })
