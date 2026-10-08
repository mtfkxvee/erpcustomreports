import re

import frappe
import requests
from frappe.desk.form.assign_to import add as _original_assign_add

WAHA_TIMEOUT = 15


def _get_waha_config():
    url = frappe.conf.get("waha_url")
    api_key = frappe.conf.get("waha_api_key")
    session = frappe.conf.get("waha_session")
    if not url or not api_key or not session:
        frappe.throw("WAHA belum dikonfigurasi di site_config.json")
    return url, api_key, session


def normalize_wa_number(number):
    if not number:
        return None
    digits = re.sub(r"\D", "", number)
    if not digits:
        return None
    if digits.startswith("0"):
        digits = "62" + digits[1:]
    elif digits.startswith("8"):
        digits = "62" + digits
    if not digits.startswith("62"):
        return None
    return digits


def strip_html(text):
    if not text:
        return ""
    return re.sub("<[^<]+?>", " ", text).strip()


SKIP_FIELDTYPES = {
    "Section Break", "Column Break", "Tab Break", "HTML", "Button",
    "Table", "Table MultiSelect", "Signature", "Password", "Geolocation",
    "Heading", "Fold", "Code",
}
SKIP_FIELDNAMES = {"naming_series", "amended_from"}


def _format_float(value):
    v = frappe.utils.flt(value)
    if v == int(v):
        return str(int(v))
    return f"{v:.2f}".rstrip("0").rstrip(".")


def format_doc_details(doctype, docname):
    """Bikin ringkasan isi dokumen (semua field terisi) buat dikirim di pesan WA."""
    try:
        doc = frappe.get_doc(doctype, docname)
    except Exception:
        return ""

    meta = frappe.get_meta(doctype)
    site_url = frappe.utils.get_url()
    lines = []  # list of [label, display]

    for df in meta.fields:
        if df.fieldtype in SKIP_FIELDTYPES or df.fieldname in SKIP_FIELDNAMES or df.get("hidden"):
            continue

        value = doc.get(df.fieldname)
        if value in (None, "") and df.fieldtype != "Check":
            continue
        if df.fieldtype == "Int" and value == 0 and not df.get("reqd"):
            continue

        label = df.label or df.fieldname

        if df.fieldtype == "Check":
            display = "Ya" if value else "Tidak"
        elif df.fieldtype == "Currency":
            display = frappe.utils.fmt_money(value, currency=frappe.defaults.get_global_default("currency"))
        elif df.fieldtype == "Date":
            display = frappe.utils.formatdate(value)
        elif df.fieldtype == "Datetime":
            display = frappe.utils.format_datetime(value)
        elif df.fieldtype == "Float":
            display = _format_float(value)
        elif df.fieldtype in ("Text Editor", "Small Text", "Text", "Long Text"):
            display = strip_html(str(value))
        elif df.fieldtype in ("Attach", "Attach Image"):
            display = value if str(value).startswith("http") else f"{site_url}{value}"
        else:
            display = str(value)

        display = str(display).strip()
        if not display:
            continue

        # gabung field Satuan/UOM ke baris numerik sebelumnya (mis. "Jarak Tempuh Normal: 2 KILOMETER")
        is_uom_field = df.fieldtype == "Select" and (
            (df.label or "").strip().lower() in ("satuan", "uom", "unit") or df.fieldname.endswith("_uom")
        )
        if is_uom_field and lines:
            lines[-1][1] = f"{lines[-1][1]} {display}"
            continue

        lines.append([label, display])

    return "\n".join(f"*{l}:* {d}" for l, d in lines)


@frappe.whitelist()
def send_whatsapp_message(to, text):
    url, api_key, session = _get_waha_config()
    chat_id = f"{to}@c.us"
    try:
        resp = requests.post(
            f"{url}/api/sendText",
            headers={"X-Api-Key": api_key, "Content-Type": "application/json"},
            json={"session": session, "chatId": chat_id, "text": text},
            timeout=WAHA_TIMEOUT,
        )
        resp.raise_for_status()
        return True
    except Exception:
        frappe.log_error(title=f"Gagal kirim WA ke {to}")
        return False


@frappe.whitelist()
def assign_to_add_with_wa(args=None, *, ignore_permissions=False):
    """Override for frappe.desk.form.assign_to.add — kirim WA kalau checkbox 'send_wa' dicentang."""
    if not args:
        args = frappe.local.form_dict

    send_wa = frappe.utils.cint(args.get("send_wa"))

    result = _original_assign_add(args, ignore_permissions=ignore_permissions)

    if send_wa:
        try:
            assign_to_list = frappe.parse_json(args.get("assign_to")) or []
            doctype = args.get("doctype")
            docname = args.get("name")
            description = strip_html(args.get("description"))
            site_url = frappe.utils.get_url()
            doc_route = frappe.scrub(doctype).replace("_", "-")
            doc_link = f"{site_url}/app/{doc_route}/{docname}"
            details = format_doc_details(doctype, docname)

            message = f"*Tugas Baru: {doctype} - {docname}*\n"
            if description:
                message += f"\n{description}\n"
            if details:
                message += f"\n{details}\n"
            message += f"\nLink: {doc_link}"

            for user in assign_to_list:
                wa_number = frappe.db.get_value("User", user, "custom_whatsapp_number")
                normalized = normalize_wa_number(wa_number)
                if not normalized:
                    continue
                send_whatsapp_message(normalized, message)
        except Exception:
            frappe.log_error(title="assign_to_add_with_wa: gagal kirim notifikasi WA")

    return result


# ---------------------------------------------------------------------------
# WhatsApp Blast via api.co.id (Official WhatsApp Business API / Meta Cloud API)
# ---------------------------------------------------------------------------

def _get_apicoid_config():
    url = frappe.conf.get("apicoid_url")
    api_key = frappe.conf.get("apicoid_api_key")
    if not url or not api_key:
        frappe.throw("api.co.id belum dikonfigurasi di site_config.json")
    return url, api_key


def send_apicoid_template_message(phone, template_name, language="id", variables=None):
    """Kirim WhatsApp template message via api.co.id (WhatsApp Official API).

    Return dict: {"success": bool, "error": str or None}
    """
    url, api_key = _get_apicoid_config()

    components = []
    if variables:
        components.append({
            "type": "body",
            "parameters": [{"type": "text", "text": str(v)} for v in variables],
        })

    payload = {
        "channel": "whatsapp",
        "message_type": "template",
        "phone_number": phone,
        "template": {
            "name": template_name,
            "language": {"code": language or "id"},
        },
    }
    if components:
        payload["template"]["components"] = components

    try:
        resp = requests.post(
            f"{url}/messages/send",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=WAHA_TIMEOUT,
        )
        data = resp.json() if resp.content else {}
        if resp.status_code < 300 and data.get("success"):
            return {"success": True, "error": None}
        err = data.get("error", {})
        message = err.get("message") if isinstance(err, dict) else (str(err) or f"HTTP {resp.status_code}")
        return {"success": False, "error": message}
    except Exception as e:
        return {"success": False, "error": str(e)}


def send_apicoid_text_message(phone, message):
    """Kirim WhatsApp teks bebas via api.co.id (WhatsApp Official API).

    CATATAN: Meta cuma izinkan teks bebas ke nomor yang punya sesi aktif
    (nomor tsb pernah chat ke bisnis dalam 24 jam terakhir) -- beda dengan
    template message yang boleh dipakai untuk cold outreach/blast.

    Return dict: {"success": bool, "error": str or None}
    """
    url, api_key = _get_apicoid_config()

    payload = {
        "channel": "whatsapp",
        "message_type": "text",
        "phone_number": phone,
        "content": message,
    }

    try:
        resp = requests.post(
            f"{url}/messages/send",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=WAHA_TIMEOUT,
        )
        data = resp.json() if resp.content else {}
        if resp.status_code < 300 and data.get("success"):
            return {"success": True, "error": None}
        err = data.get("error", {})
        err_message = err.get("message") if isinstance(err, dict) else (str(err) or f"HTTP {resp.status_code}")
        return {"success": False, "error": err_message}
    except Exception as e:
        return {"success": False, "error": str(e)}
