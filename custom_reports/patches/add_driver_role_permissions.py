import frappe
from frappe.permissions import add_permission, update_permission_property

ROLE = "DRIVER"
# doctype -> permission yang diberikan ke role DRIVER
PERMS = {
    "Delivery Request": ("read", "write", "create", "report", "print"),
    "Driver Activity": ("read",),
    "Outlet": ("read",),
    "Vehicle": ("read",),
    "Sales Order": ("read",),
    "Sales Invoice": ("read",),
    "Stock Entry": ("read",),
}


def execute():
    """Role DRIVER + permission untuk form Delivery Request. Idempotent (aman dijalankan ulang).

    Employee sengaja tidak diberi (berisi data HR); Sales Order/Sales Invoice/Stock Entry read-only.
    add_permission() menyalin permission standar ke Custom DocPerm dulu kalau doctype belum punya,
    jadi baris role lama (System Manager, POSNext Cashier, dst) tidak hilang.
    """
    if not frappe.db.exists("Role", ROLE):
        frappe.get_doc({"doctype": "Role", "role_name": ROLE, "desk_access": 1}).insert(
            ignore_permissions=True
        )

    for doctype, ptypes in PERMS.items():
        add_permission(doctype, ROLE, 0)
        for ptype in ptypes:
            update_permission_property(doctype, ROLE, 0, ptype, 1)

    frappe.db.commit()
    frappe.clear_cache()
