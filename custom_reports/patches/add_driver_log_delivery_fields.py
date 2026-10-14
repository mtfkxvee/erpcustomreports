import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    """Custom Field Driver Log: jenis_pengiriman (khusus aksi Selesai) & id_pengiriman (Transit &
    Selesai) -- sebelumnya digabung ke teks notes, sekarang field sendiri biar `notes` murni
    catatan bebas dari driver. Idempotent (aman dijalankan ulang)."""
    create_custom_fields({
        "Driver Log": [
            {"fieldname": "jenis_pengiriman", "label": "Jenis Pengiriman", "fieldtype": "Select",
             "options": "\nPengiriman Customer\nPengiriman FMCG\nPengiriman F&H.S\nPengiriman MBG"
                        "\nPengiriman Belanja\nLainnya",
             "insert_after": "notes"},
            {"fieldname": "id_pengiriman", "label": "ID Pengiriman", "fieldtype": "Small Text",
             "insert_after": "jenis_pengiriman"},
        ],
    })
