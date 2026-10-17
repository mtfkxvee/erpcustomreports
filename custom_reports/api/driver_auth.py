"""Generate API key untuk role DRIVER / ADMIN DRIVER (login dari aplikasi driver).

Kenapa ada modul ini: `frappe.core.doctype.user.user.generate_keys` diawali
`frappe.only_for("System Manager")`, dan field api_key/api_secret ada di permlevel 1. Role lain
tidak bisa generate key sendiri, dan batasan itu sengaja TIDAK dilonggarkan di Frappe.

Dua endpoint (POST saja), dua-duanya hanya untuk akun yang role eksplisitnya persis DRIVER:
- generate_my_api_key(): DRIVER / ADMIN DRIVER untuk dirinya sendiri.
- generate_api_key_for_driver(user): ADMIN DRIVER / System Manager untuk user berrole DRIVER saja.

Pakai di aplikasi:  Authorization: token <api_key>:<api_secret>
API key tidak punya masa berlaku; generate ulang mematikan key lama. Secret hanya dikembalikan
sekali di respons ini (disimpan terenkripsi di Frappe, tidak bisa dibaca ulang).
"""

import frappe
from frappe import _
from frappe.utils.password import set_encrypted_password

SELF_ROLES = {"DRIVER", "ADMIN DRIVER"}
MANAGER_ROLES = {"ADMIN DRIVER", "System Manager"}
MANAGED_ROLE = "DRIVER"


def _explicit_roles(user):
    return set(
        frappe.get_all("Has Role", filters={"parenttype": "User", "parent": user}, pluck="role")
    )


def _issue_key(user, actor):
    api_key = frappe.db.get_value("User", user, "api_key") or frappe.generate_hash(length=15)
    api_secret = frappe.generate_hash(length=15)

    # Tulis langsung (bukan doc.save) supaya tidak lewat validate/Server Script User, dan
    # supaya tidak menyentuh field lain. Transaksi di-commit otomatis di akhir request POST.
    frappe.db.set_value("User", user, "api_key", api_key, update_modified=False)
    set_encrypted_password("User", user, api_secret, "api_secret")
    frappe.clear_cache(user=user)

    frappe.get_doc(
        {
            "doctype": "Comment",
            "comment_type": "Info",
            "reference_doctype": "User",
            "reference_name": user,
            "content": "API key digenerate ulang oleh {0} (key lama tidak berlaku lagi).".format(actor),
        }
    ).insert(ignore_permissions=True)

    return {
        "user": user,
        "api_key": api_key,
        "api_secret": api_secret,
        "authorization": "token {0}:{1}".format(api_key, api_secret),
        "note": "Simpan sekarang. Secret tidak bisa ditampilkan lagi; generate ulang membatalkan key lama.",
    }


@frappe.whitelist(methods=["POST"])
def generate_my_api_key():
    user = frappe.session.user
    if user in ("Guest", "Administrator"):
        frappe.throw(_("Tidak diizinkan"), frappe.PermissionError)

    if not (_explicit_roles(user) & SELF_ROLES):
        frappe.throw(_("Hanya untuk role DRIVER atau ADMIN DRIVER"), frappe.PermissionError)

    return _issue_key(user, actor=user)


@frappe.whitelist(methods=["POST"])
def generate_api_key_for_driver(user: str):
    actor = frappe.session.user
    if actor in ("Guest",):
        frappe.throw(_("Tidak diizinkan"), frappe.PermissionError)

    if actor != "Administrator" and not (_explicit_roles(actor) & MANAGER_ROLES):
        frappe.throw(_("Hanya untuk ADMIN DRIVER atau System Manager"), frappe.PermissionError)

    if not frappe.db.exists("User", user):
        frappe.throw(_("User tidak ditemukan"), frappe.DoesNotExistError)

    if user == actor:
        frappe.throw(_("Gunakan generate_my_api_key untuk akun sendiri"), frappe.PermissionError)

    if not frappe.db.get_value("User", user, "enabled"):
        frappe.throw(_("User sedang disabled"), frappe.ValidationError)

    # Hanya user yang role eksplisitnya persis DRIVER: ADMIN DRIVER tidak bisa menyentuh kasir,
    # System Manager, sesama ADMIN DRIVER, atau akun tanpa role.
    if _explicit_roles(user) != {MANAGED_ROLE}:
        frappe.throw(
            _("Hanya untuk user yang role-nya DRIVER saja"), frappe.PermissionError
        )

    return _issue_key(user, actor=actor)
