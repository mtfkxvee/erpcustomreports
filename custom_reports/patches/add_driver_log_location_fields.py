import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    """Custom Field Driver Log: alamat_lokasi/latitude/longitude (geotagging aksi Mulai/Transit/
    Selesai/Akhiri Hari). Idempotent (aman dijalankan ulang)."""
    create_custom_fields({
        "Driver Log": [
            {"fieldname": "alamat_lokasi", "label": "Alamat Lokasi", "fieldtype": "Small Text",
             "insert_after": "custom_foto", "read_only": 1},
            {"fieldname": "latitude", "label": "Latitude", "fieldtype": "Float", "precision": "6",
             "insert_after": "alamat_lokasi", "read_only": 1},
            {"fieldname": "longitude", "label": "Longitude", "fieldtype": "Float", "precision": "6",
             "insert_after": "latitude", "read_only": 1},
        ],
    })
