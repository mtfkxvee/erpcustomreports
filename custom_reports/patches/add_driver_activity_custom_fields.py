import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    """Custom Field Driver Activity: kategori/km (Pengeluaran), jenis_kendala (Kendala), dan
    alamat_lokasi/latitude/longitude (geotagging Pengecekan). Idempotent (aman dijalankan ulang)."""
    create_custom_fields({
        "Driver Activity": [
            {"fieldname": "kategori", "label": "Kategori", "fieldtype": "Select",
             "options": "\nBBM\nToll\nParkir\nMakan\nLainnya", "insert_after": "vehicle",
             "in_list_view": 1, "in_standard_filter": 1,
             "depends_on": "eval:doc.tipe==\"Pengeluaran\""},
            {"fieldname": "km", "label": "KM", "fieldtype": "Int", "insert_after": "kategori",
             "depends_on": "eval:doc.tipe==\"Pengeluaran\" && doc.kategori==\"BBM\""},
            {"fieldname": "jenis_kendala", "label": "Jenis Kendala", "fieldtype": "Select",
             "options": "\nKendaraan bermasalah\nAkses lokasi terhalang\nBarang rusak\nLainnya",
             "insert_after": "km", "in_standard_filter": 1,
             "depends_on": "eval:doc.tipe==\"Kendala\""},
            {"fieldname": "alamat_lokasi", "label": "Alamat Lokasi", "fieldtype": "Small Text",
             "insert_after": "jenis_kendala", "read_only": 1,
             "depends_on": "eval:doc.tipe==\"Pengecekan\""},
            {"fieldname": "latitude", "label": "Latitude", "fieldtype": "Float", "precision": "6",
             "insert_after": "alamat_lokasi", "read_only": 1,
             "depends_on": "eval:doc.tipe==\"Pengecekan\""},
            {"fieldname": "longitude", "label": "Longitude", "fieldtype": "Float", "precision": "6",
             "insert_after": "latitude", "read_only": 1,
             "depends_on": "eval:doc.tipe==\"Pengecekan\""},
        ],
    })
