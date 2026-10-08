"""Inti stok Shelving.

Meniru cara kerja warehouse di ERPNext:
  - Shelving Ledger Entry = buku besar (seperti Stock Ledger Entry), append-only
  - Shelving Bin          = saldo per (shelving, item) (seperti Bin)

Stok shelving adalah SUBSET dari stok warehouse-nya. Warehouse tetap sumber kebenaran;
shelving hanya menjawab "barang warehouse ini ada di rak mana".
"""
import hashlib

import frappe
from frappe import _
from frappe.utils import flt, nowdate

EPS = 1e-6


def bin_name(shelving, item_code):
    """Nama Shelving Bin deterministik -> PK menjamin 1 baris per (shelving, item)."""
    return hashlib.md5(f"{shelving}|{item_code}".encode()).hexdigest()[:20]


def _locked_bin(shelving, warehouse, item_code):
    name = bin_name(shelving, item_code)
    if not frappe.db.exists("Shelving Bin", name):
        try:
            frappe.get_doc({
                "doctype": "Shelving Bin", "shelving": shelving, "warehouse": warehouse,
                "item_code": item_code, "actual_qty": 0,
            }).insert(ignore_permissions=True)
        except frappe.DuplicateEntryError:
            pass  # dibuat proses lain di saat yang sama
    return frappe.db.sql(
        "select name, actual_qty from `tabShelving Bin` where name = %s for update",
        name, as_dict=True,
    )[0]


def post_entry(shelving, warehouse, item_code, qty, voucher_type, voucher_no,
               voucher_detail_no=None, posting_date=None, company=None, is_cancelled=0):
    """Tambah/kurangi stok satu shelving. Menolak saldo negatif."""
    qty = flt(qty)
    if not qty:
        return
    row = _locked_bin(shelving, warehouse, item_code)
    new_qty = flt(row.actual_qty) + qty
    if new_qty < -EPS:
        frappe.throw(
            _("Stok shelving {0} untuk item {1} tidak cukup: tersedia {2}, dibutuhkan {3}.").format(
                frappe.bold(shelving), frappe.bold(item_code),
                flt(row.actual_qty), abs(qty)))
    frappe.db.set_value("Shelving Bin", row.name, "actual_qty", new_qty, update_modified=False)
    frappe.get_doc({
        "doctype": "Shelving Ledger Entry",
        "posting_date": posting_date or nowdate(),
        "shelving": shelving, "warehouse": warehouse, "item_code": item_code,
        "actual_qty": qty, "qty_after_transaction": new_qty,
        "voucher_type": voucher_type, "voucher_no": voucher_no,
        "voucher_detail_no": voucher_detail_no, "company": company,
        "is_cancelled": is_cancelled,
    }).insert(ignore_permissions=True)


def reverse_voucher(voucher_type, voucher_no, lenient=False):
    """Batalkan semua entry sebuah voucher dengan entry kebalikan (jejak audit tetap ada).

    lenient=True: pembalikan yang akan membuat saldo rak negatif dipotong sebesar saldo yang ada
    (sisanya dikoreksi sync_item), supaya pembatalan dokumen ERPNext tidak pernah tertahan rak.
    """
    rows = frappe.get_all(
        "Shelving Ledger Entry",
        filters={"voucher_type": voucher_type, "voucher_no": voucher_no, "is_cancelled": 0},
        fields=["name", "shelving", "warehouse", "item_code", "actual_qty",
                "voucher_detail_no", "company", "posting_date"],
        order_by="creation desc",
    )
    for r in rows:
        undo = -flt(r.actual_qty)
        if lenient and undo < 0:
            have = flt(_locked_bin(r.shelving, r.warehouse, r.item_code).actual_qty)
            undo = -min(abs(undo), max(have, 0))
        post_entry(r.shelving, r.warehouse, r.item_code, undo, voucher_type,
                   voucher_no, r.voucher_detail_no, r.posting_date, r.company, is_cancelled=1)
        frappe.db.set_value("Shelving Ledger Entry", r.name, "is_cancelled", 1,
                            update_modified=False)


def get_shelved_qty(warehouse, item_code):
    return flt(frappe.db.sql(
        "select sum(actual_qty) from `tabShelving Bin` where warehouse = %s and item_code = %s",
        (warehouse, item_code))[0][0])


def get_unshelved_qty(warehouse, item_code):
    """Stok warehouse yang belum ditempatkan di shelving mana pun."""
    wh_qty = flt(frappe.db.get_value("Bin", {"warehouse": warehouse, "item_code": item_code},
                                     "actual_qty"))
    return wh_qty - get_shelved_qty(warehouse, item_code)

# ------------------------------------------------- rak bawaan & sinkronisasi
DEFAULT_SHELVING_NAME = "BELUM DITATA"
DEFAULT_PRIORITY = 9999


def get_default_shelving(warehouse, create=False):
    """Rak penampung stok yang belum ditentukan rak aslinya (selalu terakhir diambil)."""
    name = frappe.db.get_value("Shelving", {"warehouse": warehouse, "is_default": 1})
    if not name and create:
        name = frappe.get_doc({
            "doctype": "Shelving", "shelving_name": DEFAULT_SHELVING_NAME,
            "warehouse": warehouse, "is_default": 1, "priority": DEFAULT_PRIORITY,
        }).insert(ignore_permissions=True).name
    return name


def _sync_voucher(warehouse):
    return frappe._dict(
        doctype="Shelving Sync", name=f"SYNC-{nowdate()}", posting_date=nowdate(),
        company=frappe.db.get_value("Warehouse", warehouse, "company"))


def sync_item(warehouse, item_code, voucher=None):
    """Samakan total rak dengan stok warehouse (Bin) untuk satu item.

    Warehouse lebih besar -> selisih masuk rak BELUM DITATA.
    Warehouse lebih kecil -> selisih dikurangi: BELUM DITATA dulu, lalu rak berprioritas terkecil.
    """
    if not _has_shelves(warehouse):
        return
    diff = get_unshelved_qty(warehouse, item_code)  # stok warehouse - total rak
    if abs(diff) <= EPS:
        return
    v = voucher or _sync_voucher(warehouse)
    if diff > 0:
        post_entry(get_default_shelving(warehouse, create=True), warehouse, item_code, diff,
                   v.doctype, v.name, None, v.get("posting_date"), v.get("company"))
        return
    excess = -diff
    default = get_default_shelving(warehouse)
    if default:
        take = min(excess, max(flt(_locked_bin(default, warehouse, item_code).actual_qty), 0))
        if take > EPS:
            post_entry(default, warehouse, item_code, -take, v.doctype, v.name, None,
                       v.get("posting_date"), v.get("company"))
            excess -= take
    if excess > EPS:
        _deduct(v, item_code, warehouse, excess)


def sync_warehouse(warehouse):
    """Koreksi semua item di satu warehouse yang totalnya tidak sama dengan rak."""
    rows = frappe.db.sql(
        """select item_code from (
               select item_code, sum(wq) as wq, sum(sq) as sq from (
                   select item_code, actual_qty as wq, 0 as sq from `tabBin` where warehouse = %s
                   union all
                   select item_code, 0, actual_qty from `tabShelving Bin` where warehouse = %s
               ) t group by item_code
           ) x where abs(wq - sq) > 0.000001""",
        (warehouse, warehouse))
    for (item_code,) in rows:
        sync_item(warehouse, item_code)
    return len(rows)


def sync_all():
    """Jadwal per jam: jaring pengaman untuk perubahan stok yang lolos dari hook dokumen."""
    for wh in frappe.get_all("Shelving", filters={"disabled": 0}, pluck="warehouse", distinct=True):
        try:
            n = sync_warehouse(wh)
            frappe.db.commit()
            if n:
                frappe.logger("shelving").info(f"sync {wh}: {n} item dikoreksi")
        except Exception:
            frappe.db.rollback()
            frappe.log_error(title=f"Shelving: sync gagal {wh}")


def _sync_pairs(doc, pairs):
    for warehouse, item_code in pairs:
        sync_item(warehouse, item_code, doc)


def _voucher_pairs(doc):
    pairs = set(frappe.db.sql(
        "select distinct warehouse, item_code from `tabStock Ledger Entry` "
        "where voucher_type = %s and voucher_no = %s", (doc.doctype, doc.name)))
    pairs |= set(frappe.db.sql(
        "select distinct warehouse, item_code from `tabShelving Ledger Entry` "
        "where voucher_type = %s and voucher_no = %s", (doc.doctype, doc.name)))
    return pairs


# ------------------------------------------------- pengurangan otomatis
def _has_shelves(warehouse):
    return bool(warehouse) and bool(
        frappe.db.exists("Shelving", {"warehouse": warehouse, "disabled": 0}))


def _deduct(doc, item_code, warehouse, qty, detail=None):
    """Kurangi shelving dengan prioritas terkecil dulu (rak 1 habis -> rak 2, dst).
    Sisa yang tak punya shelving dibiarkan (stok warehouse tetap berkurang normal)."""
    remaining = qty
    shelves = frappe.db.sql(
        """select sb.shelving from `tabShelving Bin` sb
           join `tabShelving` s on s.name = sb.shelving
           where sb.warehouse = %s and sb.item_code = %s and sb.actual_qty > 0
           order by s.priority asc, sb.creation asc""",
        (warehouse, item_code), as_dict=True)
    for s in shelves:
        if remaining <= EPS:
            break
        available = flt(_locked_bin(s.shelving, warehouse, item_code).actual_qty)
        take = min(remaining, available)
        if take > EPS:
            post_entry(s.shelving, warehouse, item_code, -take, doc.doctype, doc.name, detail,
                       doc.get("posting_date"), doc.get("company"))
            remaining -= take


def _restock(doc, item_code, warehouse, qty):
    """Retur penjualan: kembalikan ke shelving asal, maksimal sebesar yang belum dikembalikan."""
    original = doc.get("return_against")
    if not original:
        return  # retur tanpa dokumen asal: biarkan belum ber-shelving, bisa di-put-away manual
    vouchers = [original] + frappe.get_all(
        doc.doctype, filters={"return_against": original, "docstatus": 1}, pluck="name")
    net = frappe.db.sql(
        """select shelving, sum(actual_qty) as qty from `tabShelving Ledger Entry`
           where voucher_type = %s and voucher_no in %s and item_code = %s
             and warehouse = %s and is_cancelled = 0
           group by shelving having sum(actual_qty) < 0""",
        (doc.doctype, tuple(vouchers), item_code, warehouse), as_dict=True)
    remaining = qty
    for n in net:
        if remaining <= EPS:
            break
        give = min(remaining, abs(flt(n.qty)))
        post_entry(n.shelving, warehouse, item_code, give, doc.doctype, doc.name, None,
                   doc.get("posting_date"), doc.get("company"))
        remaining -= give


def _voucher_changes(doc):
    """Perubahan stok warehouse sebuah voucher, dibaca dari Stock Ledger Entry (sumber kebenaran)."""
    return frappe.db.sql(
        """select warehouse, item_code, sum(actual_qty) as qty from `tabStock Ledger Entry`
           where voucher_type = %s and voucher_no = %s and is_cancelled = 0
           group by warehouse, item_code having sum(actual_qty) != 0""",
        (doc.doctype, doc.name), as_dict=True)


def _guarded(savepoint, title):
    """Jalankan bagian shelving tanpa pernah memblokir transaksi utama; gagal -> rollback + Error Log."""
    def decorator(fn):
        def wrapper(doc, method=None):
            frappe.db.savepoint(savepoint)
            try:
                fn(doc)
            except Exception:
                frappe.db.rollback(save_point=savepoint)
                frappe.log_error(title=f"Shelving: {title} {doc.doctype} {doc.name}")
        return wrapper
    return decorator


@_guarded("shelving_voucher", "gagal update stok shelving")
def on_voucher_submit(doc):
    """Sales Invoice, Delivery Note, Purchase Receipt, Purchase Invoice: stok warehouse keluar ->
    rak ikut dikurangi; masuk -> rak BELUM DITATA (retur penjualan: rak asal). Lalu disamakan."""
    for ch in _voucher_changes(doc):
        if not _has_shelves(ch.warehouse):
            continue
        if flt(ch.qty) < 0:
            _deduct(doc, ch.item_code, ch.warehouse, -flt(ch.qty))
        elif doc.get("is_return"):
            _restock(doc, ch.item_code, ch.warehouse, flt(ch.qty))
        sync_item(ch.warehouse, ch.item_code, doc)


@_guarded("shelving_voucher", "gagal update stok shelving")
def on_reconciliation_submit(doc):
    """Stock Reconciliation: rak disamakan dengan hasil rekonsiliasi warehouse."""
    _sync_pairs(doc, {(r.warehouse, r.item_code) for r in doc.items})


@_guarded("shelving_voucher", "gagal membatalkan stok shelving")
def on_voucher_cancel(doc):
    reverse_voucher(doc.doctype, doc.name, lenient=True)
    _sync_pairs(doc, _voucher_pairs(doc))


# --------------------------------------------------------------- Warehouse
def validate_warehouse(doc, method=None):
    """Hanya warehouse non-group yang dicentang 'Pakai Shelving' boleh punya rak."""
    if doc.get("use_shelving") and doc.is_group:
        frappe.throw(_("Warehouse group tidak boleh memakai shelving."))
    if not doc.get("use_shelving") and not doc.is_new() and frappe.db.exists(
            "Shelving", {"warehouse": doc.name, "disabled": 0}):
        frappe.throw(_("Warehouse ini masih punya shelving aktif, nonaktifkan semua shelving-nya "
                       "(setelah dikosongkan) sebelum menghapus centang Pakai Shelving."))


# ------------------------------------------------------------- Stock Entry
def validate_stock_entry(doc, method=None):
    """Shelving yang diisi harus milik warehouse barisnya dan (untuk tujuan) aktif."""
    for row in doc.items:
        for field, wh in (("from_shelving", row.s_warehouse), ("to_shelving", row.t_warehouse)):
            shelving = row.get(field)
            if not shelving:
                continue
            sh_wh, disabled = frappe.db.get_value("Shelving", shelving, ["warehouse", "disabled"])
            if sh_wh != wh:
                frappe.throw(_("Baris {0}: shelving {1} bukan milik warehouse {2}.").format(
                    row.idx, shelving, wh))
            if disabled and field == "to_shelving":
                frappe.throw(_("Baris {0}: shelving {1} nonaktif.").format(row.idx, shelving))


def require_target_shelving(doc, method=None):
    """Apa pun jenis Stock Entry-nya: tujuan warehouse yang punya shelving WAJIB isi Ke Shelving."""
    for row in doc.items:
        if row.t_warehouse and _has_shelves(row.t_warehouse) and not row.to_shelving:
            frappe.throw(_("Baris {0}: isi <b>Ke Shelving</b>, warehouse {1} memakai shelving.").format(
                row.idx, row.t_warehouse))


def on_stock_entry_submit(doc, method=None):
    auto = {}  # keluar dari warehouse berrak tanpa Dari Shelving -> kurangi otomatis
    for row in doc.items:
        qty = flt(row.transfer_qty)
        meta = (doc.doctype, doc.name, row.name, doc.posting_date, doc.company)
        if row.from_shelving:
            post_entry(row.from_shelving, row.s_warehouse, row.item_code, -qty, *meta)
        elif row.s_warehouse and _has_shelves(row.s_warehouse):
            key = (row.s_warehouse, row.item_code)
            auto[key] = auto.get(key, 0) + qty
        if row.to_shelving:
            post_entry(row.to_shelving, row.t_warehouse, row.item_code, qty, *meta)
    for (warehouse, item_code), qty in auto.items():
        _deduct(doc, item_code, warehouse, qty)
    # apa pun yang belum tertata (mis. dari-rak kosong di sisi masuk) disamakan dengan warehouse
    _sync_pairs(doc, {(w, r.item_code) for r in doc.items for w in (r.s_warehouse, r.t_warehouse) if w})


def on_stock_entry_cancel(doc, method=None):
    reverse_voucher(doc.doctype, doc.name, lenient=True)
    _sync_pairs(doc, _voucher_pairs(doc))
