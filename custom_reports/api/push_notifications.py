import frappe
import requests
from google.oauth2 import service_account
import google.auth.transport.requests

FCM_SCOPES = ["https://www.googleapis.com/auth/firebase.messaging"]
FCM_TIMEOUT = 15


def _get_service_account_path():
    path = frappe.conf.get("firebase_service_account_path")
    if not path:
        frappe.throw("Firebase belum dikonfigurasi di site_config.json (firebase_service_account_path)")
    return path


def _get_fcm_access_token():
    """Tukar service account key jadi access token OAuth2 khusus scope FCM. Access token-nya
    dipakai sekali pakai per request (Google rekomendasiin cache, tapi volume kirim kita rendah
    jadi nggak perlu optimasi itu dulu)."""
    credentials = service_account.Credentials.from_service_account_file(
        _get_service_account_path(), scopes=FCM_SCOPES
    )
    credentials.refresh(google.auth.transport.requests.Request())
    return credentials.token, credentials.project_id


def send_push_notification(fcm_token, title, body, data=None):
    """Kirim 1 push notification ke 1 device token lewat FCM HTTP v1 API. Return True/False,
    nggak pernah raise -- pemanggil (doc_event hook dkk) jangan sampai gagal total gara2 ini."""
    if not fcm_token:
        return False
    try:
        access_token, project_id = _get_fcm_access_token()
    except Exception:
        frappe.log_error(title="Gagal ambil access token FCM")
        return False

    message = {
        "message": {
            "token": fcm_token,
            "notification": {"title": title, "body": body},
        }
    }
    if data:
        message["message"]["data"] = {str(k): str(v) for k, v in data.items()}

    try:
        resp = requests.post(
            f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send",
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            json=message,
            timeout=FCM_TIMEOUT,
        )
        resp.raise_for_status()
        return True
    except Exception:
        frappe.log_error(title=f"Gagal kirim push notification ({title})")
        return False


@frappe.whitelist()
def save_fcm_token(token=None):
    """Dipanggil mobile app abis dapet FCM device token -- simpen ke User.custom_fcm_token milik
    AKUN YG LAGI LOGIN (frappe.session.user, bukan parameter dari client -- biar nggak bisa
    disalahgunakan buat nulis token ke akun orang lain). Sengaja BUKAN lewat PUT /api/resource/User
    biasa (erpUpdateDoc), krn role "DRIVER" (dipakai hampir semua kurir) belum tentu punya izin
    tulis ke doctype User -- sama persis kasusnya kayak field `_assign` di Delivery Request yg
    dulu kena masalah serupa (lihat erpAssignTo di mobile). frappe.db.set_value() di sini jalan di
    level DB langsung, lewatin pengecekan permission dokumen, jadi reliable buat semua role."""
    if not token:
        return {"success": False, "message": "Token kosong"}
    frappe.db.set_value("User", frappe.session.user, "custom_fcm_token", token)
    frappe.db.commit()
    return {"success": True}


def notify_on_delivery_assignment(doc, method):
    """doc_event on_update Delivery Request -- kirim push notification ke driver pas field
    `driver` baru keisi/berubah (assignment baru). Dipasang di hooks.py (BUKAN numpang di
    override_whitelisted_methods punya WhatsApp) krn `driver` sering diisi langsung lewat form,
    bukan selalu lewat tombol Assign To."""
    if not doc.has_value_changed("driver") or not doc.driver:
        return
    try:
        user_id = frappe.db.get_value("Employee", doc.driver, "user_id")
        if not user_id:
            return
        fcm_token = frappe.db.get_value("User", user_id, "custom_fcm_token")
        if not fcm_token:
            return
        title = "Pesanan Baru"
        body = ", ".join(filter(None, [doc.customer_name, doc.outlet])) or f"Pesanan {doc.name}"
        send_push_notification(fcm_token, title, body, data={
            "doctype": "Delivery Request",
            "docname": doc.name,
        })
    except Exception:
        frappe.log_error(title="notify_on_delivery_assignment: gagal kirim push notification")
