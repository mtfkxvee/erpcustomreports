import math
import statistics
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import add_days, date_diff, flt, getdate

# Rekomendasi Safety Stock, Stock Minimum (reorder point) dan Stock Maximum per item di 1 warehouse,
# dihitung dari histori penjualan & pergerakan stok. Hanya membaca data, tidak menyimpan apa pun.
#
#   ADS = total terjual / hari stok tersedia (hari stok kosong tidak dihitung, pembagi minimal 14 hari)
#   SS  = Z x akar(LT x sd^2 + ADS^2 x sLT^2)
#   Min = ADS x LT + SS
#   Max = Min + ADS x siklus order

MAX_HARI = 186
MIN_PEMBAGI = 14
LT_HISTORI_HARI = 180       # histori PO -> Purchase Receipt untuk lead time
LT_MIN, LT_MAX = 1, 30
SIKLUS_DEFAULT = 7
SIKLUS_MIN, SIKLUS_MAX = 3, 30
BATAS_A, BATAS_B = 0.80, 0.95

# produk virtual (token PLN, pulsa, e-wallet) bukan barang fisik
EXCLUDE_ITEM_GROUPS = ("TOPUP",)
EXCLUDE_UOMS = ("RP",)

VOUCHER_JUAL = ("Sales Invoice", "POS Invoice")
VOUCHER_BELI = ("Purchase Receipt", "Purchase Invoice")

S_HABIS = "Habis"
S_ORDER = "Perlu Order"
S_AMAN = "Aman"
S_OVER = "Overstock"
S_TIDAK_LAKU = "Tidak Laku"
S_TIDAK_AKTIF = "Tidak Aktif"


def execute(filters=None):
    filters = frappe._dict(filters or {})
    if not filters.get("warehouse") or not filters.get("from_date") or not filters.get("to_date"):
        frappe.msgprint(
            "Silakan pilih <b>Warehouse</b>, <b>Histori Dari</b> dan <b>Histori Sampai</b> terlebih dahulu.",
            indicator="orange", alert=True,
        )
        return [], []

    dari, sampai = getdate(filters.from_date), getdate(filters.to_date)
    if sampai < dari:
        frappe.throw(_("Histori Sampai tidak boleh sebelum Histori Dari"))
    if date_diff(sampai, dari) + 1 > MAX_HARI:
        frappe.throw(_("Rentang histori maksimal {0} hari").format(MAX_HARI))

    z = {
        "A": nilai_z(filters.get("sl_a"), 98),
        "B": nilai_z(filters.get("sl_b"), 95),
        "C": nilai_z(filters.get("sl_c"), 90),
        "D": 0,
    }
    lt_transfer = max(int(flt(filters.get("lt_transfer")) or 3), LT_MIN)

    rows = hitung(filters.warehouse, dari, sampai, z, lt_transfer)
    rows = saring(rows, filters)

    hitung_status = defaultdict(int)
    for r in rows:
        hitung_status[r["status"]] += 1
    summary = [
        {"label": _("Jumlah Item"), "value": len(rows), "datatype": "Int", "indicator": "Blue"},
        {"label": _(S_HABIS), "value": hitung_status[S_HABIS], "datatype": "Int", "indicator": "Red"},
        {"label": _(S_ORDER), "value": hitung_status[S_ORDER], "datatype": "Int", "indicator": "Orange"},
        {"label": _(S_AMAN), "value": hitung_status[S_AMAN], "datatype": "Int", "indicator": "Green"},
        {"label": _(S_OVER), "value": hitung_status[S_OVER], "datatype": "Int", "indicator": "Blue"},
        {"label": _(S_TIDAK_LAKU), "value": hitung_status[S_TIDAK_LAKU], "datatype": "Int", "indicator": "Grey"},
    ]
    message = (
        f"Histori {date_diff(sampai, dari) + 1} hari. ADS dihitung hanya dari hari stok tersedia. "
        "Safety Stock = Z x akar(LT x sd&sup2; + ADS&sup2; x sLT&sup2;); Min = ADS x LT + SS; "
        "Max = Min + ADS x Siklus Order. Kelas ABC dari nilai HPP terjual di seluruh warehouse "
        f"(A 80%, B 15%, C 5%, D tidak laku); Z: A {z['A']:.2f}, B {z['B']:.2f}, C {z['C']:.2f}. "
        "Saran Order belum memperhitungkan kelipatan dus / minimum order supplier."
    )
    return get_columns(), rows, message, None, summary


def nilai_z(persen, default):
    p = flt(persen) or default
    p = min(max(p, 50), 99.9)
    return statistics.NormalDist().inv_cdf(p / 100)


# ---------------------------------------------------------------- data


def hitung(warehouse, dari, sampai, z, lt_transfer):
    n_hari = date_diff(sampai, dari) + 1

    bins = frappe.db.sql(
        """
        SELECT b.item_code, b.actual_qty, b.stock_uom, i.item_name, i.item_group, i.disabled
        FROM `tabBin` b
        JOIN `tabItem` i ON i.name = b.item_code
        WHERE b.warehouse = %(wh)s AND i.is_stock_item = 1
          AND i.item_group NOT IN %(grp)s AND b.stock_uom NOT IN %(uom)s
        """,
        {"wh": warehouse, "grp": EXCLUDE_ITEM_GROUPS, "uom": EXCLUDE_UOMS},
        as_dict=True,
    )

    sle = frappe.db.sql(
        """
        SELECT item_code, posting_date, voucher_type, actual_qty, qty_after_transaction,
               stock_value_difference
        FROM `tabStock Ledger Entry`
        WHERE warehouse = %(wh)s AND is_cancelled = 0
          AND posting_date BETWEEN %(dari)s AND %(sampai)s
        ORDER BY posting_date, posting_time, creation
        """,
        {"wh": warehouse, "dari": dari, "sampai": sampai},
        as_list=True,
    )
    per_item = defaultdict(list)
    for e in sle:
        per_item[e[0]].append(e)

    # saldo terakhir sebelum periode = stok awal hari pertama
    saldo_awal = dict(frappe.db.sql(
        """
        SELECT item_code, qty_after_transaction FROM (
            SELECT item_code, qty_after_transaction,
                   ROW_NUMBER() OVER (PARTITION BY item_code
                                      ORDER BY posting_date DESC, posting_time DESC, creation DESC) AS rn
            FROM `tabStock Ledger Entry`
            WHERE warehouse = %(wh)s AND is_cancelled = 0 AND posting_date < %(dari)s
        ) t
        WHERE rn = 1
        """,
        {"wh": warehouse, "dari": dari},
    ))

    lt_item, lt_supplier, supplier_terakhir = get_lead_time(warehouse, sampai)
    semua_lt = [x for v in lt_supplier.values() for x in v]
    lt_global = statistics.median(semua_lt) if semua_lt else 3
    sd_lt_global = stdev(semua_lt)

    rows = []
    for b in bins:
        code = b.item_code
        ents = per_item.get(code) or []
        stok = flt(b.actual_qty)
        if b.disabled and not ents and stok == 0:
            continue

        jual = [0.0] * n_hari
        tutup = [None] * n_hari
        tgl_terima = set()
        qty_beli = qty_transfer = nilai_jual = 0.0
        awal = flt(saldo_awal.get(code, 0 if ents else stok))
        for _code, tgl, vtype, qty, saldo, nilai in ents:
            i = date_diff(tgl, dari)
            qty = flt(qty)
            if vtype in VOUCHER_JUAL:
                jual[i] -= qty
                nilai_jual -= flt(nilai)
            elif qty > 0 and vtype in VOUCHER_BELI:
                tgl_terima.add(i)
                qty_beli += qty
            elif qty > 0 and vtype == "Stock Entry":
                tgl_terima.add(i)
                qty_transfer += qty
            tutup[i] = flt(saldo)

        # hari stok kosong tidak dihitung: jual 0 di hari itu karena barangnya tidak ada
        tersedia, hari_kosong, sebelum = [], 0, awal
        for i in range(n_hari):
            if tutup[i] is None:
                tutup[i] = sebelum
            if sebelum > 0 or tutup[i] > 0 or jual[i] > 0:
                tersedia.append(max(jual[i], 0))
            else:
                hari_kosong += 1
            sebelum = tutup[i]

        total_jual = sum(jual)
        ads = total_jual / max(len(tersedia), MIN_PEMBAGI) if total_jual > 0 else 0
        sd = stdev(tersedia) if total_jual > 0 else 0

        supplier = supplier_terakhir.get(code)
        lt_i = lt_item.get(code) or []
        if len(lt_i) >= 2:
            lt, sd_lt, sumber_lt = statistics.median(lt_i), stdev(lt_i), f"PO item ({len(lt_i)})"
        elif qty_transfer > qty_beli:
            lt, sd_lt, sumber_lt = lt_transfer, 0, "Default transfer"
        elif supplier and lt_supplier.get(supplier):
            v = lt_supplier[supplier]
            lt, sd_lt, sumber_lt = statistics.median(v), stdev(v), f"PO supplier ({len(v)})"
        elif lt_i:
            lt, sd_lt, sumber_lt = lt_i[0], sd_lt_global, "PO item (1)"
        else:
            lt, sd_lt, sumber_lt = lt_global, sd_lt_global, "Median global"
        lt = min(max(lt, LT_MIN), LT_MAX)

        terima = sorted(tgl_terima)
        if len(terima) >= 2:
            siklus = statistics.median([b2 - b1 for b1, b2 in zip(terima, terima[1:], strict=False)])
        else:
            siklus = SIKLUS_DEFAULT
        siklus = min(max(siklus, SIKLUS_MIN), SIKLUS_MAX)

        if qty_beli == 0 and qty_transfer == 0:
            sumber = ""
        elif qty_transfer > qty_beli:
            sumber = "Transfer"
        else:
            sumber = "Supplier"

        rows.append(frappe._dict(
            item_code=code, item_name=b.item_name, item_group=b.item_group, uom=b.stock_uom,
            supplier=supplier, sumber=sumber, nilai_jual=nilai_jual, total_jual=total_jual,
            hari_jual=sum(1 for q in jual if q > 0), hari_tersedia=len(tersedia), hari_kosong=hari_kosong,
            ads=ads, sd=sd, lead_time=lt, sd_lt=sd_lt, sumber_lt=sumber_lt, siklus=siklus, stok=stok,
        ))

    beri_kelas(rows)
    for r in rows:
        hitung_min_max(r, z[r.kelas])

    urutan = {"A": 0, "B": 1, "C": 2, "D": 3}
    rows.sort(key=lambda r: (urutan[r.kelas], -r.nilai_jual))
    return rows


def get_lead_time(warehouse, sampai):
    """Lead time = tanggal PO -> tanggal Purchase Receipt pertama per PO-item ke warehouse ini."""
    data = frappe.db.sql(
        """
        SELECT pri.item_code, pri.purchase_order, pr.supplier, pr.posting_date, po.transaction_date
        FROM `tabPurchase Receipt Item` pri
        JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
        LEFT JOIN `tabPurchase Order` po ON po.name = pri.purchase_order
        WHERE pri.warehouse = %(wh)s AND pr.docstatus = 1
          AND pr.posting_date BETWEEN %(dari)s AND %(sampai)s
        ORDER BY pr.posting_date, pr.posting_time
        """,
        {"wh": warehouse, "dari": add_days(sampai, -LT_HISTORI_HARI), "sampai": sampai},
        as_dict=True,
    )
    lt_item, lt_supplier, supplier_terakhir, sudah = defaultdict(list), defaultdict(list), {}, set()
    for r in data:
        supplier_terakhir[r.item_code] = r.supplier
        if not r.purchase_order or not r.transaction_date:
            continue
        kunci = (r.purchase_order, r.item_code)
        if kunci in sudah:
            continue
        sudah.add(kunci)
        hari = date_diff(r.posting_date, r.transaction_date)
        if hari < 0 or hari > 60:
            continue
        lt_item[r.item_code].append(hari)
        lt_supplier[r.supplier].append(hari)
    return lt_item, lt_supplier, supplier_terakhir


def beri_kelas(rows):
    laku = sorted((r for r in rows if r.nilai_jual > 0), key=lambda r: -r.nilai_jual)
    total = sum(r.nilai_jual for r in laku)
    kumulatif = 0
    for r in laku:
        kumulatif += r.nilai_jual
        p = kumulatif / total
        r.kelas = "A" if p <= BATAS_A else "B" if p <= BATAS_B else "C"
    for r in rows:
        if not r.get("kelas"):
            r.kelas = "C" if r.total_jual > 0 else "D"


def hitung_min_max(r, z):
    r.z = z
    if r.ads <= 0:
        r.safety_stock = r.min_qty = r.max_qty = 0
    else:
        r.safety_stock = math.ceil(z * math.sqrt(r.lead_time * r.sd**2 + r.ads**2 * r.sd_lt**2))
        r.min_qty = math.ceil(r.ads * r.lead_time + r.safety_stock)
        r.max_qty = math.ceil(r.min_qty + r.ads * r.siklus)

    r.cukup_hari = round(max(r.stok, 0) / r.ads, 1) if r.ads > 0 else None
    r.saran_order = 0
    if r.ads <= 0:
        r.status = S_TIDAK_LAKU if r.stok > 0 else S_TIDAK_AKTIF
    elif r.stok <= 0:
        r.status = S_HABIS
    elif r.stok < r.min_qty:
        r.status = S_ORDER
    elif r.stok > r.max_qty:
        r.status = S_OVER
    else:
        r.status = S_AMAN
    if r.ads > 0 and r.stok < r.min_qty:
        r.saran_order = math.ceil(r.max_qty - max(r.stok, 0))


def saring(rows, filters):
    if filters.get("item_group"):
        lft, rgt = frappe.db.get_value("Item Group", filters.item_group, ["lft", "rgt"])
        grup = set(frappe.get_all("Item Group", filters={"lft": [">=", lft], "rgt": ["<=", rgt]}, pluck="name"))
        rows = [r for r in rows if r.item_group in grup]
    if filters.get("kelas"):
        rows = [r for r in rows if r.kelas == filters.kelas]
    status = filters.get("status")
    if status == "Habis + Perlu Order":
        rows = [r for r in rows if r.status in (S_HABIS, S_ORDER)]
    elif status:
        rows = [r for r in rows if r.status == status]
    return rows


def stdev(nilai):
    return statistics.stdev(nilai) if len(nilai) >= 2 else 0


# ---------------------------------------------------------------- kolom


def get_columns():
    return [
        {"fieldname": "item_code", "label": _("Item"), "fieldtype": "Link", "options": "Item", "width": 130},
        {"fieldname": "item_name", "label": _("Nama Item"), "fieldtype": "Data", "width": 220},
        {"fieldname": "item_group", "label": _("Item Group"), "fieldtype": "Link", "options": "Item Group", "width": 130},
        {"fieldname": "uom", "label": _("UOM"), "fieldtype": "Data", "width": 60},
        {"fieldname": "kelas", "label": _("Kelas"), "fieldtype": "Data", "width": 60},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "stok", "label": _("Stok Sekarang"), "fieldtype": "Float", "width": 100},
        {"fieldname": "safety_stock", "label": _("Safety Stock"), "fieldtype": "Int", "width": 95},
        {"fieldname": "min_qty", "label": _("Stock Min"), "fieldtype": "Int", "width": 90},
        {"fieldname": "max_qty", "label": _("Stock Max"), "fieldtype": "Int", "width": 90},
        {"fieldname": "saran_order", "label": _("Saran Order"), "fieldtype": "Int", "width": 95},
        {"fieldname": "cukup_hari", "label": _("Cukup (hari)"), "fieldtype": "Float", "precision": 1, "width": 90},
        {"fieldname": "total_jual", "label": _("Total Terjual"), "fieldtype": "Float", "width": 100},
        {"fieldname": "nilai_jual", "label": _("Nilai HPP Terjual"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "ads", "label": _("Rata-rata Jual/Hari"), "fieldtype": "Float", "precision": 2, "width": 110},
        {"fieldname": "sd", "label": _("Std Dev Jual/Hari"), "fieldtype": "Float", "precision": 2, "width": 110},
        {"fieldname": "hari_jual", "label": _("Hari Ada Jual"), "fieldtype": "Int", "width": 90},
        {"fieldname": "hari_tersedia", "label": _("Hari Stok Ada"), "fieldtype": "Int", "width": 90},
        {"fieldname": "hari_kosong", "label": _("Hari Stok Kosong"), "fieldtype": "Int", "width": 100},
        {"fieldname": "lead_time", "label": _("Lead Time (hari)"), "fieldtype": "Float", "precision": 1, "width": 100},
        {"fieldname": "sd_lt", "label": _("Std Dev Lead Time"), "fieldtype": "Float", "precision": 2, "width": 100},
        {"fieldname": "sumber_lt", "label": _("Sumber Lead Time"), "fieldtype": "Data", "width": 130},
        {"fieldname": "siklus", "label": _("Siklus Order (hari)"), "fieldtype": "Float", "precision": 1, "width": 110},
        {"fieldname": "z", "label": _("Z"), "fieldtype": "Float", "precision": 2, "width": 60},
        {"fieldname": "sumber", "label": _("Sumber Pasokan"), "fieldtype": "Data", "width": 100},
        {"fieldname": "supplier", "label": _("Supplier Terakhir"), "fieldtype": "Link", "options": "Supplier", "width": 130},
    ]
