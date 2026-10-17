import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    """Driver Activity: alamat_lokasi/latitude/longitude sebelumnya cuma muncul (depends_on) di
    form ERP pas tipe "Pengecekan" -- sekarang mobile app geotag SEMUA tipe aktivitas (Pengeluaran/
    Kendala/Cuci Kendaraan juga, bukan cuma Pengecekan lagi), jadi depends_on-nya dilepas biar
    kelihatan di form apa pun tipe-nya. create_custom_fields() default update=True, jadi field yg
    udah ada (dari add_driver_activity_custom_fields.py) di-update properti-nya di sini, bukan
    dibuat dobel. Idempotent (aman dijalankan ulang)."""
    create_custom_fields({
        "Driver Activity": [
            {"fieldname": "alamat_lokasi", "label": "Alamat Lokasi", "fieldtype": "Small Text",
             "insert_after": "jenis_kendala", "read_only": 1, "depends_on": ""},
            {"fieldname": "latitude", "label": "Latitude", "fieldtype": "Float", "precision": "6",
             "insert_after": "alamat_lokasi", "read_only": 1, "depends_on": ""},
            {"fieldname": "longitude", "label": "Longitude", "fieldtype": "Float", "precision": "6",
             "insert_after": "latitude", "read_only": 1, "depends_on": ""},
        ],
    })
