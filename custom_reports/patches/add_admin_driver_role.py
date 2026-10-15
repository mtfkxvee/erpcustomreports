import frappe
from frappe.permissions import add_permission, update_permission_property

from custom_reports.patches.add_driver_role_permissions import PERMS as DRIVER_PERMS

ROLE = "ADMIN DRIVER"

# Permission tambahan di atas permission DRIVER: doctype -> {permlevel: ptype}
EXTRA_PERMS = {
    "User": {0: ("read", "write", "create"), 1: ("read", "write")},
    "Employee": {0: ("read", "write", "create")},
}

GUARD_NAME = "User - Guard ADMIN DRIVER"
QUERY_NAME = "User - Daftar User ADMIN DRIVER"

# Catatan sandbox Server Script: tanpa import, tanpa .format(), tanpa nama variabel berawalan
# underscore, tanpa frappe.get_traceback (lihat docs/delivery-request.md 2026-09-22/24).
GUARD_SCRIPT = '''
actor = frappe.session.user
actor_roles = []
for row in frappe.db.sql("select role from `tabHas Role` where parenttype = 'User' and parent = %s", [actor], as_list=1):
    actor_roles.append(row[0])

if actor != "Administrator" and "ADMIN DRIVER" in actor_roles and "System Manager" not in actor_roles:
    allowed = ["DRIVER"]

    if doc.name in ["Administrator", "Guest"]:
        frappe.throw("ADMIN DRIVER tidak boleh mengubah user " + doc.name)

    for r in doc.get("roles") or []:
        if r.role not in allowed:
            frappe.throw("ADMIN DRIVER hanya boleh memberi role DRIVER. Role ditolak: " + str(r.role))

    if doc.get("role_profile_name"):
        frappe.throw("ADMIN DRIVER tidak boleh memakai Role Profile")
    if len(doc.get("role_profiles") or []) > 0:
        frappe.throw("ADMIN DRIVER tidak boleh memakai Role Profile")

    if not doc.is_new():
        before = doc.get_doc_before_save()
        if before:
            old_roles = []
            for r in before.get("roles") or []:
                old_roles.append(r.role)
            if len(old_roles) == 0:
                frappe.throw("ADMIN DRIVER hanya boleh mengubah user yang berrole DRIVER")
            for role in old_roles:
                if role not in allowed:
                    frappe.throw("ADMIN DRIVER hanya boleh mengubah user yang berrole DRIVER saja")
            if before.get("user_type") != doc.get("user_type"):
                frappe.throw("ADMIN DRIVER tidak boleh mengubah User Type")
'''

QUERY_SCRIPT = '''
conditions = ""
actor = frappe.session.user
if actor != "Administrator":
    actor_roles = []
    for row in frappe.db.sql("select role from `tabHas Role` where parenttype = 'User' and parent = %s", [actor], as_list=1):
        actor_roles.append(row[0])
    if "ADMIN DRIVER" in actor_roles and "System Manager" not in actor_roles:
        conditions = "(`tabUser`.name = " + frappe.db.escape(actor) + " or `tabUser`.name in (select parent from `tabHas Role` where parenttype = 'User' and role = 'DRIVER'))"
'''


def _upsert_server_script(name, script_type, reference_doctype, script, doctype_event=None):
    values = {
        "script_type": script_type,
        "reference_doctype": reference_doctype,
        "script": script.strip() + "\n",
    }
    if doctype_event:
        values["doctype_event"] = doctype_event

    if frappe.db.exists("Server Script", name):
        doc = frappe.get_doc("Server Script", name)
        doc.update(values)
        doc.disabled = 0
        doc.save(ignore_permissions=True)
    else:
        frappe.get_doc({"doctype": "Server Script", "name": name, **values}).insert(
            ignore_permissions=True
        )


def execute():
    """Role ADMIN DRIVER: permission DRIVER + boleh bikin/ubah User (hanya berrole DRIVER) dan Employee.

    Pengaman ada di Server Script (bukan di permission): tanpa itu permlevel 1 di User membuat role ini
    setara System Manager. Idempotent (aman dijalankan ulang). Tidak butuh restart.
    """
    if not frappe.db.exists("Role", ROLE):
        frappe.get_doc({"doctype": "Role", "role_name": ROLE, "desk_access": 1}).insert(
            ignore_permissions=True
        )

    for doctype, ptypes in DRIVER_PERMS.items():
        add_permission(doctype, ROLE, 0)
        for ptype in ptypes:
            update_permission_property(doctype, ROLE, 0, ptype, 1)

    for doctype, levels in EXTRA_PERMS.items():
        for permlevel, ptypes in levels.items():
            add_permission(doctype, ROLE, permlevel)
            for ptype in ptypes:
                update_permission_property(doctype, ROLE, permlevel, ptype, 1)

    # Pengaman dibuat SEBELUM role dipakai siapa pun; urutan di sini sengaja setelah permission
    # tapi dalam transaksi yang sama, jadi tidak ada jendela role aktif tanpa pengaman.
    _upsert_server_script(GUARD_NAME, "DocType Event", "User", GUARD_SCRIPT, "Before Save")
    _upsert_server_script(QUERY_NAME, "Permission Query", "User", QUERY_SCRIPT)

    frappe.db.commit()
    frappe.clear_cache()
