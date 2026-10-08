import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    """Custom Field fitur Shelving. Idempotent (aman dijalankan ulang)."""
    create_custom_fields({
        "Stock Entry Detail": [
            {"fieldname": "from_shelving", "label": "Dari Shelving", "fieldtype": "Link",
             "options": "Shelving", "insert_after": "s_warehouse", "in_list_view": 1, "no_copy": 1,
             "description": "Kosong = dikurangi otomatis dari shelving berprioritas terkecil"},
            {"fieldname": "to_shelving", "label": "Ke Shelving", "fieldtype": "Link",
             "options": "Shelving", "insert_after": "t_warehouse", "in_list_view": 1, "no_copy": 1,
             "description": "Wajib diisi bila warehouse tujuan memakai shelving"},
        ],
        "Warehouse": [
            {"fieldname": "use_shelving", "label": "Pakai Shelving", "fieldtype": "Check",
             "insert_after": "is_group", "depends_on": "eval:!doc.is_group", "no_copy": 1,
             "description": "Centang hanya untuk warehouse tempat barang disusun di rak (mis. XSM 1). "
                            "Warehouse penerimaan (Selling Area) dan parent group jangan dicentang."},
        ],
    })
