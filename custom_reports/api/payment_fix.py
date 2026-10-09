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

Pemakaian:
    POST /api/method/custom_reports.api.payment_fix.change_payment_mode
    invoice, from_mode, to_mode, reason, dry_run (default 1)

dry_run=1 hanya mengembalikan rencana perubahan. Tulis betulan butuh dry_run=0.

Setup user:
    bench --site <site> execute custom_reports.api.payment_fix.create_fixer_user
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate

ROLE = "Payment Mode Fixer"
EMAIL = "hermes-accounting@x-sha.id"
FULL_NAME = "Hermes Accounting (Payment Mode Fixer)"

ALLOWED_TYPES = ("Cash", "Bank", "General")


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


@frappe.whitelist(methods=["POST"])
def change_payment_mode(invoice, from_mode, to_mode, reason, dry_run=1):
    frappe.only_for(ROLE)

    dry_run = str(dry_run) not in ("0", "false", "False")
    reason = (reason or "").strip()
    if len(reason) < 5:
        frappe.throw(_("reason wajib diisi (minimal 5 karakter) untuk audit"))
    if from_mode == to_mode:
        frappe.throw(_("from_mode dan to_mode sama"))

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
                f"nominal {flt(row.base_amount)}. Oleh {frappe.session.user}. Alasan: {reason}"
            ),
        }
    ).insert(ignore_permissions=True)
    frappe.db.commit()

    return plan


def create_fixer_user(regenerate=0):
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
    if not frappe.db.exists("User", EMAIL):
        user = frappe.new_doc("User")
        user.email = EMAIL
        user.first_name = FULL_NAME
        user.enabled = 1
        user.send_welcome_email = 0
        user.insert(ignore_permissions=True)
        created = True

    user = frappe.get_doc("User", EMAIL)
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

    out = {"user": EMAIL, "role": ROLE, "user_dibuat": created, "api_key": user.api_key}
    if secret:
        out["token"] = f"{user.api_key}:{secret}"
    return out
