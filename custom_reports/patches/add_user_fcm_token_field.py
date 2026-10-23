import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    """Custom Field User: custom_fcm_token -- nyimpen token device Firebase Cloud Messaging per
    akun, diisi otomatis dari mobile app X-SHPRESS abis login sukses. Dipakai server buat kirim
    push notification (lihat custom_reports/api/push_notifications.py) pas Delivery Request
    di-assign ke driver. Pola field-nya niru custom_whatsapp_number yang udah ada. Idempotent
    (aman dijalankan ulang)."""
    create_custom_fields({
        "User": [
            {"fieldname": "custom_fcm_token", "label": "FCM Push Token", "fieldtype": "Small Text",
             "insert_after": "custom_whatsapp_number", "read_only": 1,
             "description": "Diisi otomatis oleh mobile app X-SHPRESS, jangan diubah manual."},
        ],
    })
