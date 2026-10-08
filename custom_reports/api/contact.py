import re
import frappe

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@frappe.whitelist(allow_guest=True)
def submit_contact_message(nama=None, email=None, subjek=None, pesan=None, website=None):
    # Honeypot: field tersembunyi di form, harus selalu kosong dari user asli.
    # Kalau keisi, itu tanda bot -- pura-pura sukses tapi gak disimpan.
    if website:
        return {"success": True}

    nama = (nama or "").strip()
    email = (email or "").strip()
    subjek = (subjek or "").strip()
    pesan = (pesan or "").strip()

    if not nama or len(nama) > 140:
        frappe.throw("Nama wajib diisi (maksimal 140 karakter)")
    if not email or not EMAIL_RE.match(email) or len(email) > 140:
        frappe.throw("Format email tidak valid")
    if not pesan or len(pesan) > 5000:
        frappe.throw("Pesan wajib diisi (maksimal 5000 karakter)")
    if len(subjek) > 200:
        frappe.throw("Subjek terlalu panjang")

    doc = frappe.get_doc({
        "doctype": "Website Contact Message",
        "nama": nama,
        "email": email,
        "subjek": subjek,
        "pesan": pesan,
        "status": "New",
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    return {"success": True, "name": doc.name}
