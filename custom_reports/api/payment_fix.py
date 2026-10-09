"""Koreksi mode pembayaran Sales Invoice lewat API, tanpa akses DB langsung.

Kenapa ada: agent (Hermes accounting) kadang perlu membetulkan invoice yang
mode pembayarannya salah input (mis. BTN seharusnya CASH). Sebelumnya itu
dikerjakan dengan UPDATE SQL mentah memakai db_password — artinya siapa pun yang
bisa menjalankannya memegang kredensial DB produksi. Endpoint ini menggantikan
itu: scope-nya satu hal saja, dan semua validasi ada di sini.

Yang boleh berubah: mode_of_payment, type, account di baris Sales Invoice Payment,
kolom account di GL Entry sisi debit invoice itu, dan kolom against di GL Entry
yang menunjuk akun lama (sisi piutang), serta expected_amount/difference di
POS Closing Shift yang memuat invoice itu (closing_amount kasir tidak disentuh). Nominal TIDAK pernah
berubah. Payment Ledger Entry tidak disentuh karena dia mencatat piutang
customer, bukan akun kas/bank.

Pemanggil wajib punya role ROLE (lihat create_fixer_user). Role itu sengaja
TANPA DocPerm apa pun — izinnya hanya untuk memanggil method ini.

Pemakaian (agent eksternal, mis. ALE):
    1. POST .../custom_reports.api.payment_fix.change_payment_mode
       invoice, from_mode, to_mode, reason, dry_run=1      -> rencana, tidak menulis
    2. POST .../custom_reports.api.payment_fix.request_payment_mode_change
       invoice, from_mode, to_mode, reason                 -> server kirim ringkasan
       + KODE ke WhatsApp admin (payfix_admin_wa). Kode tidak dikembalikan ke agent.
    3. Admin memberi kode ke agent (DM).
    4. POST .../change_payment_mode dengan dry_run=0 dan approval_code=<kode>.

Eksekusi tanpa kode yang sah ditolak server. Kode berlaku 30 menit, sekali pakai,
terikat pada invoice + mode + alasan yang sama, dan hangus setelah 3 kali salah.

Setup user:
    bench --site <site> execute custom_reports.api.payment_fix.create_fixer_user
"""

import hmac
import secrets

import frappe
from frappe import _
from frappe.utils import flt, getdate

ROLE = "Payment Mode Fixer"
EMAIL = "ale@x-sha.id"
FULL_NAME = "ALE (Payment Mode Fixer)"

ALLOWED_TYPES = ("Cash", "Bank", "General")

# Alasan bawaan kalau pemanggil tidak menyebutkan. Dipakai sama di request dan eksekusi,
# jadi tanda tangan persetujuan tetap cocok.
DEFAULT_REASON = "Salah input kasir"

# Persetujuan admin dipaksa server: eksekusi (dry_run=0) wajib membawa kode yang
# HANYA dikirim server ke WhatsApp admin (site_config: payfix_admin_wa, pisahkan
# koma). Agent tidak pernah menerima kode itu dari API; dia baru tahu kalau admin
# memberikannya.
APPROVAL_TTL = 30 * 60
APPROVAL_MAX_ATTEMPTS = 3


def _account_for(mode, company):
    account = frappe.db.get_value(
        "Mode of Payment Account",
        {"parent": mode, "company": company},
        "default_account",
    )
    if not account:
        frappe.throw(_("Mode of Payment {0} belum punya akun untuk company {1}").format(mode, company))
    return account


def _check_period_open(posting_date, company):
    frozen = frappe.db.get_single_value("Accounts Settings", "acc_frozen_upto")
    if frozen and getdate(posting_date) <= getdate(frozen):
        frappe.throw(_("Akun dibekukan sampai {0}, invoice tanggal {1} tidak bisa diubah").format(frozen, posting_date))

    closed = frappe.db.exists(
        "Period Closing Voucher",
        {"company": company, "docstatus": 1, "posting_date": [">=", posting_date]},
    )
    if closed:
        frappe.throw(_("Periode sudah ditutup ({0}), invoice tanggal {1} tidak bisa diubah").format(closed, posting_date))


def _gl_checks(inv, row, gl, from_account, to_account):
    """Pengecekan GL untuk dry-run. Tiap item: {check, ok, detail}.

    Semua harus ok sebelum perubahan boleh ditulis.
    """
    checks = []

    def add(name, ok, detail):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    company_currency = frappe.get_cached_value("Company", inv.company, "default_currency")
    gl_total = sum(flt(g.debit) for g in gl)
    base_amount = flt(row.base_amount)

    add(
        "debit GL = nominal pembayaran",
        abs(gl_total - base_amount) <= 0.01,
        f"total debit GL {gl_total} vs base_amount pembayaran {base_amount}",
    )

    # Seluruh GL voucher harus seimbang, sebelum maupun sesudah perubahan
    # (hanya kolom account yang berubah, jadi totalnya tidak bergeser).
    tot = frappe.db.sql(
        """select sum(debit), sum(credit) from `tabGL Entry`
        where voucher_type='Sales Invoice' and voucher_no=%s and is_cancelled=0""",
        inv.name,
    )[0]
    td, tc = flt(tot[0]), flt(tot[1])
    add("GL voucher seimbang", abs(td - tc) <= 0.01, f"total debit {td} vs total credit {tc}")

    to_currency = frappe.db.get_value("Account", to_account, "account_currency")
    for g in gl:
        cur = g.account_currency
        if cur == company_currency:
            expected = flt(g.debit)
        elif cur == inv.currency and flt(row.amount):
            expected = flt(row.amount)
        else:
            expected = None

        if expected is None:
            add(
                f"debit_in_account_currency {g.name}",
                False,
                f"mata uang akun {cur} tidak cocok dengan company ({company_currency}) maupun invoice ({inv.currency})",
            )
        else:
            add(
                f"debit_in_account_currency {g.name}",
                abs(flt(g.debit_in_account_currency) - expected) <= 0.01,
                f"debit_in_account_currency {flt(g.debit_in_account_currency)} vs seharusnya {expected} ({cur})",
            )

        # Kolom *_in_account_currency tidak ikut diubah, jadi mata uang akun tujuan
        # wajib sama dengan akun asal; kalau beda, nilainya jadi salah.
        add(
            f"mata uang akun tujuan {g.name}",
            to_currency == cur,
            f"akun asal {from_account} = {cur}, akun tujuan {to_account} = {to_currency}",
        )

    return checks


def _shift_plan(inv, row, from_mode, to_mode, checks):
    """Rencana koreksi rekonsiliasi POS Closing Shift (pilihan A).

    Hanya `expected_amount` dan `difference` yang berubah. `closing_amount` adalah
    angka hitungan kasir, TIDAK disentuh. Shift TIDAK di-cancel/amend: on_cancel
    membatalkan merge log dan consolidated invoice. Menutup shift juga tidak
    membuat GL, jadi koreksi ini tidak mengubah buku besar.

    Mengembalikan None kalau invoice tidak ada di shift mana pun.
    """
    refs = frappe.get_all(
        "Sales Invoice Reference",
        filters={"sales_invoice": inv.name, "parenttype": "POS Closing Shift"},
        fields=["parent"],
    )
    if not refs:
        return None
    if len(refs) > 1:
        checks.append(
            {"check": "POS Closing Shift", "ok": False, "detail": f"invoice ada di {len(refs)} shift; periksa manual"}
        )
        return None

    shift = refs[0].parent
    sh = frappe.db.get_value("POS Closing Shift", shift, ["docstatus", "pos_profile"], as_dict=True)
    if sh.docstatus != 1:
        checks.append({"check": "POS Closing Shift", "ok": False, "detail": f"{shift} bukan submitted"})
        return None

    cash_mode = frappe.db.get_value("POS Profile", sh.pos_profile, "posa_cash_mode_of_payment") or "Cash"
    change = flt(frappe.db.get_value("Sales Invoice", inv.name, "base_change_amount"))
    if abs(change) > 0.01:
        checks.append(
            {"check": "POS Closing Shift", "ok": False, "detail": f"invoice punya kembalian {change}; periksa manual"}
        )
        return None

    details = {
        d.mode_of_payment: d
        for d in frappe.get_all(
            "POS Closing Shift Detail",
            filters={"parent": shift},
            fields=["name", "mode_of_payment", "opening_amount", "expected_amount", "closing_amount"],
        )
    }
    missing = [m for m in (from_mode, to_mode) if m not in details]
    if missing:
        checks.append(
            {"check": "POS Closing Shift", "ok": False, "detail": f"{shift} tidak punya baris rekonsiliasi {', '.join(missing)}"}
        )
        return None

    amount = flt(row.base_amount)
    perubahan = []
    for mode, delta in ((from_mode, -amount), (to_mode, amount)):
        d = details[mode]
        # Hitung ulang expected dari invoice (rumus sama dengan pos_next:
        # kembalian dikurangkan hanya dari mode cash) lalu bandingkan dengan yang
        # tersimpan. Kalau beda, shift sudah bergeser dari sebab lain.
        rows = frappe.db.sql(
            """select sip.base_amount, si.base_change_amount
            from `tabSales Invoice Reference` r
            join `tabSales Invoice` si on si.name = r.sales_invoice
            join `tabSales Invoice Payment` sip on sip.parent = si.name
            where r.parent = %s and si.docstatus = 1 and sip.mode_of_payment = %s""",
            (shift, mode),
        )
        hitung = flt(d.opening_amount)
        for base_amount, change_amount in rows:
            hitung += flt(base_amount)
            if mode == cash_mode:
                hitung -= flt(change_amount)

        cocok = abs(hitung - flt(d.expected_amount)) <= 0.01
        checks.append(
            {
                "check": f"expected shift {mode}",
                "ok": cocok,
                "detail": f"{shift}: tersimpan {flt(d.expected_amount)} vs hitung ulang {hitung}",
            }
        )
        baru = flt(d.expected_amount) + delta
        perubahan.append(
            {
                "baris": d.name,
                "mode": mode,
                "expected_sebelum": flt(d.expected_amount),
                "expected_sesudah": baru,
                "closing_amount": flt(d.closing_amount),
                "difference_sesudah": flt(d.closing_amount) - baru,
            }
        )

    return {"shift": shift, "perubahan": perubahan}


@frappe.whitelist()
def get_payment_info(invoice):
    """Baca-saja: mode pembayaran yang tercatat sekarang, plus pilihan mode tujuan.

    Peminta cukup mengirim nomor transaksi; agent memanggil ini untuk tahu mode
    sekarang (from_mode) dan mode apa yang sah di outlet itu.
    """
    frappe.only_for(ROLE)

    inv = frappe.db.get_value(
        "Sales Invoice",
        invoice,
        ["name", "docstatus", "status", "posting_date", "pos_profile", "grand_total", "is_return", "company"],
        as_dict=True,
    )
    if not inv:
        frappe.throw(_("Sales Invoice {0} tidak ditemukan").format(invoice))

    payments = frappe.get_all(
        "Sales Invoice Payment",
        filters={"parent": invoice, "parenttype": "Sales Invoice"},
        fields=["mode_of_payment", "type", "account", "amount"],
        order_by="idx",
    )
    options, mode_cash, shift = [], None, None
    if inv.pos_profile:
        mode_cash = frappe.db.get_value("POS Profile", inv.pos_profile, "posa_cash_mode_of_payment")
        options = [
            r.mode_of_payment
            for r in frappe.get_all(
                "POS Payment Method",
                filters={"parent": inv.pos_profile},
                fields=["mode_of_payment"],
                order_by="idx",
            )
        ]
    ref = frappe.get_all(
        "Sales Invoice Reference",
        filters={"sales_invoice": invoice, "parenttype": "POS Closing Shift"},
        pluck="parent",
    )
    if ref:
        shift = ref[0]

    return {
        "invoice": inv.name,
        "status": inv.status,
        "docstatus": inv.docstatus,
        "tanggal": str(inv.posting_date),
        "pos_profile": inv.pos_profile,
        "grand_total": flt(inv.grand_total),
        "is_return": inv.is_return,
        "pembayaran_sekarang": [
            {"mode": p.mode_of_payment, "type": p.type, "account": p.account, "amount": flt(p.amount)}
            for p in payments
        ],
        "mode_kas_outlet": mode_cash,
        "mode_tujuan_yang_sah": options,
        "closing_shift": shift,
        "bisa_dikoreksi": inv.docstatus == 1 and not inv.is_return and len(payments) >= 1,
    }


def _approval_key(invoice):
    return f"payfix_approval:{invoice}"


def _signature(from_mode, to_mode, reason):
    return [from_mode, to_mode, (reason or "").strip()]


def _create_approval(invoice, from_mode, to_mode, reason, requester):
    code = secrets.token_hex(4).upper()
    frappe.cache().set_value(
        _approval_key(invoice),
        {
            "code": code,
            "sig": _signature(from_mode, to_mode, reason),
            "requester": requester,
            "attempts": 0,
        },
        expires_in_sec=APPROVAL_TTL,
    )
    return code


def _verify_approval(invoice, from_mode, to_mode, reason, code):
    """Lempar error kalau tidak sah. Mengembalikan data persetujuan kalau sah."""
    key = _approval_key(invoice)
    ap = frappe.cache().get_value(key)
    if not ap:
        frappe.throw(
            _("Belum ada permintaan persetujuan yang berlaku untuk {0} (atau sudah lewat 30 menit). "
              "Jalankan request_payment_mode_change dulu.").format(invoice)
        )
    if not code:
        frappe.throw(_("approval_code wajib untuk eksekusi. Minta kodenya ke admin."))
    if ap["sig"] != _signature(from_mode, to_mode, reason):
        frappe.throw(_("Parameter tidak sama dengan yang diminta persetujuannya"))
    if not hmac.compare_digest(str(code).strip().upper(), ap["code"]):
        ap["attempts"] += 1
        if ap["attempts"] >= APPROVAL_MAX_ATTEMPTS:
            frappe.cache().delete_value(key)
            frappe.throw(_("Kode salah {0} kali. Permintaan dibatalkan; ajukan ulang.").format(APPROVAL_MAX_ATTEMPTS))
        frappe.cache().set_value(key, ap, expires_in_sec=APPROVAL_TTL)
        frappe.throw(_("Kode persetujuan salah"))
    return ap


def _notify_admins(text):
    from custom_reports.api.whatsapp import normalize_wa_number, send_whatsapp_message

    raw = frappe.conf.get("payfix_admin_wa") or ""
    numbers = [n for n in (normalize_wa_number(x) for x in str(raw).split(",")) if n]
    if not numbers:
        frappe.throw(_("payfix_admin_wa belum diset di site_config.json; permintaan tidak bisa dikirim"))
    sent = [n for n in numbers if send_whatsapp_message(n, text)]
    if not sent:
        frappe.throw(_("Gagal mengirim WhatsApp ke admin; permintaan dibatalkan"))
    return len(sent)


@frappe.whitelist(methods=["POST"])
def request_payment_mode_change(invoice, from_mode=None, to_mode=None, reason=None):
    """Ajukan koreksi: dry-run + kirim ringkasan dan kode ke WhatsApp admin.

    Kode TIDAK dikembalikan ke pemanggil. Eksekusi (change_payment_mode dengan
    dry_run=0) butuh kode itu, yang hanya diketahui admin.
    """
    frappe.only_for(ROLE)
    reason = (reason or "").strip() or DEFAULT_REASON
    plan = change_payment_mode(invoice, from_mode, to_mode, reason, dry_run=1)
    if not plan.get("siap_dieksekusi"):
        plan["status"] = "ditolak_pengecekan"
        return plan

    from_mode, to_mode = plan["dari"]["mode"], plan["ke"]["mode"]
    code = _create_approval(invoice, from_mode, to_mode, reason, frappe.session.user)

    baris = [
        "PERSETUJUAN KOREKSI MODE PEMBAYARAN",
        f"Invoice : {invoice}",
        f"Ubah    : {from_mode} ({plan['dari']['account']}) -> {to_mode} ({plan['ke']['account']})",
        f"Nominal : Rp {plan['nominal']:,.0f}",
        f"Alasan  : {reason}",
        f"Diminta : {frappe.session.user}",
    ]
    shift = plan.get("closing_shift")
    if shift:
        baris.append(f"Shift   : {shift['shift']} (closing kasir tidak diubah)")
        for p_ in shift["perubahan"]:
            baris.append(
                f"  {p_['mode']}: expected {p_['expected_sebelum']:,.0f} -> {p_['expected_sesudah']:,.0f}, "
                f"selisih {p_['difference_sesudah']:,.0f}"
            )
    else:
        baris.append("Shift   : invoice tidak masuk shift")
    baris += [
        "",
        f"KODE: {code}",
        "Berikan kode ini ke agent HANYA kalau kamu setuju. Berlaku 30 menit.",
    ]
    jumlah = _notify_admins(chr(10).join(baris))

    plan["status"] = "menunggu_persetujuan_admin"
    plan["dikirim_ke_admin"] = jumlah
    plan["berlaku_menit"] = APPROVAL_TTL // 60
    return plan


@frappe.whitelist(methods=["POST"])
def change_payment_mode(invoice, from_mode=None, to_mode=None, reason=None, dry_run=1, approval_code=None):
    frappe.only_for(ROLE)

    dry_run = str(dry_run) not in ("0", "false", "False")
    reason = (reason or "").strip() or DEFAULT_REASON
    if len(reason) < 5:
        frappe.throw(_("reason wajib diisi (minimal 5 karakter) untuk audit"))
    if not to_mode:
        frappe.throw(_("to_mode wajib diisi (boleh 'CASH' untuk kas outlet invoice itu)"))
    from_mode = (from_mode or "").strip() or None
    to_mode = str(to_mode).strip()

    inv = frappe.db.get_value(
        "Sales Invoice",
        invoice,
        ["name", "docstatus", "company", "posting_date", "currency", "pos_profile"],
        as_dict=True,
    )
    if not inv:
        frappe.throw(_("Sales Invoice {0} tidak ditemukan").format(invoice))
    if inv.docstatus != 1:
        frappe.throw(_("Sales Invoice {0} belum submitted atau sudah cancel").format(invoice))

    # to_mode "CASH" = mode kas milik POS Profile invoice ini (CASH XSL, CASH XWP, ...),
    # supaya peminta tidak perlu tahu nama persisnya dan tidak salah outlet.
    if to_mode.upper() == "CASH":
        cash = frappe.db.get_value("POS Profile", inv.pos_profile, "posa_cash_mode_of_payment") if inv.pos_profile else None
        if not cash:
            frappe.throw(_("POS Profile invoice ini tidak punya mode kas default; sebutkan nama mode persisnya"))
        to_mode = cash

    # from_mode kosong: ambil dari invoice, asal hanya ada satu baris pembayaran.
    if not from_mode:
        modes = frappe.get_all(
            "Sales Invoice Payment",
            filters={"parent": invoice, "parenttype": "Sales Invoice"},
            pluck="mode_of_payment",
        )
        if len(modes) != 1:
            frappe.throw(
                _("Invoice punya {0} baris pembayaran ({1}); sebutkan from_mode yang mau diubah").format(
                    len(modes), ", ".join(modes) or "-"
                )
            )
        from_mode = modes[0]
    if from_mode == to_mode:
        frappe.throw(_("Mode pembayaran sudah {0}; tidak ada yang perlu diubah").format(to_mode))

    to_type = frappe.db.get_value("Mode of Payment", to_mode, "type")
    if not frappe.db.exists("Mode of Payment", from_mode) or to_type is None:
        frappe.throw(_("Mode of Payment {0} / {1} tidak ditemukan").format(from_mode, to_mode))
    if to_type not in ALLOWED_TYPES:
        frappe.throw(_("Tipe {0} tidak diizinkan").format(to_type))
    if not frappe.db.get_value("Mode of Payment", to_mode, "enabled"):
        frappe.throw(_("Mode of Payment {0} nonaktif").format(to_mode))

    # Mode tujuan harus sah di POS Profile invoice. Tanpa ini, invoice outlet A
    # bisa dipindah ke kas outlet B (akunnya valid, tapi uangnya salah tempat).
    if inv.pos_profile and not frappe.db.exists(
        "POS Payment Method", {"parent": inv.pos_profile, "mode_of_payment": to_mode}
    ):
        frappe.throw(
            _("Mode {0} tidak terdaftar di POS Profile {1} milik invoice ini").format(to_mode, inv.pos_profile)
        )

    _check_period_open(inv.posting_date, inv.company)

    rows = frappe.get_all(
        "Sales Invoice Payment",
        filters={"parent": invoice, "parenttype": "Sales Invoice", "mode_of_payment": from_mode},
        fields=["name", "amount", "base_amount", "account"],
    )
    if len(rows) != 1:
        frappe.throw(
            _("Harus tepat 1 baris pembayaran {0} di {1}, ditemukan {2}").format(from_mode, invoice, len(rows))
        )
    row = rows[0]

    from_account = _account_for(from_mode, inv.company)
    to_account = _account_for(to_mode, inv.company)

    gl = frappe.get_all(
        "GL Entry",
        filters={
            "voucher_type": "Sales Invoice",
            "voucher_no": invoice,
            "account": from_account,
            "debit": [">", 0],
            "is_cancelled": 0,
        },
        fields=["name", "debit", "debit_in_account_currency", "account_currency"],
    )
    if not gl:
        frappe.throw(_("Tidak ada GL Entry debit akun {0} untuk {1}").format(from_account, invoice))

    # Sisi piutang (credit) di invoice POS menyimpan akun pembayaran di kolom
    # `against` (bisa daftar dipisah koma). Kalau tidak ikut diganti, tampilan GL
    # menunjuk akun lama walau nominal dan akunnya sudah benar.
    against_rows = []
    for a in frappe.get_all(
        "GL Entry",
        filters={
            "voucher_type": "Sales Invoice",
            "voucher_no": invoice,
            "is_cancelled": 0,
            "against": ["like", f"%{from_account}%"],
        },
        fields=["name", "against"],
    ):
        parts = [x.strip() for x in (a.against or "").split(",")]
        if from_account in parts:
            against_rows.append(
                {
                    "name": a.name,
                    "dari": a.against,
                    "ke": ", ".join(to_account if x == from_account else x for x in parts),
                }
            )

    checks = _gl_checks(inv, row, gl, from_account, to_account)
    if row.account and row.account != from_account:
        checks.append(
            {
                "check": "akun baris pembayaran",
                "ok": False,
                "detail": f"baris pembayaran menyimpan {row.account}, seharusnya {from_account}; periksa manual",
            }
        )
    gagal = [c for c in checks if not c["ok"]]

    shift_plan = _shift_plan(inv, row, from_mode, to_mode, checks)
    gagal = [c for c in checks if not c["ok"]]

    plan = {
        "invoice": invoice,
        "dari": {"mode": from_mode, "account": from_account},
        "ke": {"mode": to_mode, "account": to_account, "type": to_type},
        "nominal": flt(row.base_amount),
        "baris_pembayaran": row.name,
        "gl_entry": [
            {
                "name": g.name,
                "debit": flt(g.debit),
                "debit_in_account_currency": flt(g.debit_in_account_currency),
                "account_currency": g.account_currency,
            }
            for g in gl
        ],
        "gl_against": against_rows,
        "closing_shift": shift_plan,
        "pengecekan": checks,
        "siap_dieksekusi": not gagal,
        "dry_run": dry_run,
    }
    if gagal:
        if dry_run:
            return plan
        frappe.throw(
            _("Pengecekan GL gagal, tidak ada yang diubah: {0}").format("; ".join(c["detail"] for c in gagal))
        )
    if dry_run:
        return plan

    approval = _verify_approval(invoice, from_mode, to_mode, reason, approval_code)

    frappe.db.set_value(
        "Sales Invoice Payment",
        row.name,
        {"mode_of_payment": to_mode, "type": to_type, "account": to_account},
    )
    for g in gl:
        frappe.db.set_value("GL Entry", g.name, "account", to_account)
    for a in against_rows:
        frappe.db.set_value("GL Entry", a["name"], "against", a["ke"])
    if shift_plan:
        for p_ in shift_plan["perubahan"]:
            frappe.db.set_value(
                "POS Closing Shift Detail",
                p_["baris"],
                {"expected_amount": p_["expected_sesudah"], "difference": p_["difference_sesudah"]},
                update_modified=False,
            )
        frappe.get_doc(
            {
                "doctype": "Comment",
                "comment_type": "Info",
                "reference_doctype": "POS Closing Shift",
                "reference_name": shift_plan["shift"],
                "content": (
                    f"Rekonsiliasi dikoreksi karena {invoice}: {from_mode} -{flt(row.base_amount)}, "
                    f"{to_mode} +{flt(row.base_amount)}. closing_amount kasir tidak diubah. "
                    f"Oleh {frappe.session.user}. Alasan: {reason}"
                ),
            }
        ).insert(ignore_permissions=True)

    frappe.get_doc(
        {
            "doctype": "Comment",
            "comment_type": "Info",
            "reference_doctype": "Sales Invoice",
            "reference_name": invoice,
            "content": (
                f"Mode pembayaran diubah {from_mode} ({from_account}) -> {to_mode} ({to_account}), "
                f"nominal {flt(row.base_amount)}. Diminta oleh {approval['requester']}, "
                f"disetujui admin (kode WhatsApp). Alasan: {reason}"
            ),
        }
    ).insert(ignore_permissions=True)
    frappe.cache().delete_value(_approval_key(invoice))
    frappe.db.commit()

    return plan


def create_fixer_user(email=EMAIL, full_name=FULL_NAME, regenerate=0):
    """Bikin role + user + API key. Aman diulang.

    Sengaja TIDAK di-whitelist: hanya bisa dijalankan lewat bench execute, bukan REST.
    Role sengaja tanpa DocPerm; izinnya cuma untuk memanggil change_payment_mode.
    Secret hanya muncul sekali. Hilang? jalankan ulang dengan regenerate=1.
    """
    regenerate = str(regenerate) in ("1", "true", "True")

    if not frappe.db.exists("Role", ROLE):
        frappe.get_doc(
            {"doctype": "Role", "role_name": ROLE, "desk_access": 0, "is_custom": 1}
        ).insert(ignore_permissions=True)

    created = False
    if not frappe.db.exists("User", email):
        user = frappe.new_doc("User")
        user.email = email
        user.first_name = full_name
        user.enabled = 1
        user.send_welcome_email = 0
        user.insert(ignore_permissions=True)
        created = True

    user = frappe.get_doc("User", email)
    user.set("roles", [])
    user.append("roles", {"role": ROLE})

    secret = None
    if created or regenerate or not user.api_key:
        if not user.api_key or regenerate:
            user.api_key = frappe.generate_hash(length=15)
        secret = frappe.generate_hash(length=15)
        user.api_secret = secret
    user.save(ignore_permissions=True)
    frappe.db.commit()

    out = {"user": email, "role": ROLE, "user_dibuat": created, "api_key": user.api_key}
    if secret:
        out["token"] = f"{user.api_key}:{secret}"
    return out
