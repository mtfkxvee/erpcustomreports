import frappe
import requests

# Import defensif -- kalau `google-auth` belum ke-install pas hooks.py ini pertama kali kebaca
# (mis. urutan deploy kebalik: git pull duluan drpd pip install), JANGAN sampai ImportError di
# sini nge-crash SELURUH alur simpan Delivery Request (doc_event on_update manggil modul ini).
# Nggak ada push notif yg kekirim sampai library-nya bener ke-install, tapi app driver/dispatcher
# tetap jalan normal -- itu prioritas di atas fitur notifnya sendiri.
try:
    from google.oauth2 import service_account
    import google.auth.transport.requests

    GOOGLE_AUTH_AVAILABLE = True
except ImportError:
    GOOGLE_AUTH_AVAILABLE = False

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
    if not GOOGLE_AUTH_AVAILABLE:
        raise RuntimeError("Library google-auth belum terinstall (jalankan: bench pip install google-auth)")
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
    """doc_event on_update Delivery Request -- kirim push notification ke driver pas pesanan BARU
    KELIATAN di mobile app-nya dia buat pertama kali.

    PENTING: syarat "keliatan di app" itu BUKAN cuma `driver` keisi -- itu juga butuh
    `delivery_status` udah bukan "Pending" lagi (persis syarat yg dipakai mobile app di
    refreshDeliveries/refreshAvailableDeliveries, AppContext.js). Dulu di sini cuma ngecek
    `has_value_changed("driver")` doang -- kalau dispatcher isi driver duluan SEBELUM status-nya
    diubah ke "Ditugaskan", notifnya kekirim duluan padahal pesanannya belum muncul di app sama
    sekali (driver bingung notif ada tapi datanya nggak ada). Sekarang dicek KOMBINASI driver+
    status SEBELUM & SESUDAH save -- notif cuma nyala pas kombinasi itu baru JADI TRUE pertama
    kalinya, bukan tiap kali salah satu field-nya kesentuh.

    Ini juga sekalian nyegah notif dobel pas status lanjut berubah sendiri oleh si driver
    (mis. "Ditugaskan" -> "Dalam Perjalanan" pas dia sendiri tap "Kirim Pesanan"/mulai Transit) --
    itu bukan assignment baru, jadi SENGAJA nggak dinotif ulang."""
    if not doc.driver or doc.delivery_status == "Pending":
        return

    doc_before = doc.get_doc_before_save()
    driver_before = doc_before.get("driver") if doc_before else None
    status_before = doc_before.get("delivery_status") if doc_before else None
    was_visible_before = bool(driver_before) and status_before not in (None, "Pending")
    if was_visible_before:
        return  # udah keliatan di app sebelumnya juga -> bukan assignment baru

    try:
        user_id = frappe.db.get_value("Employee", doc.driver, "user_id")
        if not user_id:
            return
        fcm_token = frappe.db.get_value("User", user_id, "custom_fcm_token")
        if not fcm_token:
            return
        outlet_nama = frappe.db.get_value("Outlet", doc.outlet, "nama") or doc.outlet or "-"
        customer_nama = doc.customer_name or "pelanggan"
        title = "Tugas Pengiriman Baru"
        body = f"Ada pengiriman baru dari {outlet_nama} untuk {customer_nama}. Cek detail di aplikasi."
        send_push_notification(fcm_token, title, body, data={
            "doctype": "Delivery Request",
            "docname": doc.name,
        })
    except Exception:
        frappe.log_error(title="notify_on_delivery_assignment: gagal kirim push notification")
