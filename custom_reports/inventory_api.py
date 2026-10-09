# Copyright (c) 2026, X-SHA and contributors
# For license information, please see license.txt
#
# Satu API call untuk laporan "Daily Inventory" (Saldo Awal/Pembelian/Penjualan/
# Transfer Masuk/Transfer Keluar/Lainnya/Saldo Akhir) per outlet, 3 varian sekaligus
# (ALL, EXC_TOPUP, EXC_TOPUP_SEM).
#
# PERFORMA: versi awal scan SELURUH histori Stock Ledger Entry pakai window function
# (ROW_NUMBER/LAG) -> timeout di production (>120s, jutaan baris SLE). Versi ini
# jauh lebih cepat krn:
#   - Saldo Akhir dihitung dari tabBin (saldo real-time yg SELALU ter-update ERPNext,
#     bukan scan histori) dikurangi mutasi SETELAH as_of_date (biasanya cuma beberapa
#     hari kalau as_of_date baru2 ini).
#   - Mutasi harian dihitung cuma utk tanggal as_of_date itu sendiri (range sempit,
#     bukan seluruh histori dari awal).
#   - Saldo Awal = Saldo Akhir dikurangi net mutasi hari itu (identitas akuntansi
#     dasar), bukan query terpisah.
# Catatan: efisien utk as_of_date yg relatif baru (beberapa hari/minggu terakhir).
# Kalau butuh tanggal yg sangat lampau, query "mutasi setelah as_of_date" bisa jadi
# berat lagi krn rentangnya makin lebar.
#
# CATATAN PENTING: setiap outlet punya sampai 3 warehouse fisik terpisah di ERP
# (GUDANG/storage, SELLING AREA/toko, TRANSIT/dalam perjalanan). Versi awal cuma
# baca SELLING AREA sehingga saldo & transfer masuk/keluar jauh lebih kecil dari
# laporan asli. Versi ini menjumlahkan SEMUA warehouse per outlet.
#
# URL: /api/method/custom_reports.inventory_api.get_daily_inventory?as_of_date=YYYY-MM-DD

import calendar
from decimal import ROUND_HALF_DOWN, ROUND_HALF_UP, Decimal

import frappe

_OUTLET_WAREHOUSES = {
    "XSC": ["GUDANG XSC - X", "SELLING AREA XSC - X", "TRANSIT XSC - X"],
    "XSC-OL": ["GUDANG XSC-OL - X"],
    "PSR": ["GUDANG PSR - X", "SELLING AREA PSR - X", "TRANSIT PSR - X"],
    "XPY": ["GUDANG XPY - X", "SELLING AREA XPY - X", "TRANSIT XPY - X"],
    "XJB": ["GUDANG XJB - X", "SELLING AREA XJB - X", "TRANSIT XJB - X"],
    "XCW": ["GUDANG XCW - X", "SELLING AREA XCW - X", "TRANSIT XCW - X"],
    "OCW": ["GUDANG OCW - X"],
    "XSP": ["GUDANG XSP - X", "SELLING AREA XSP - X", "TRANSIT XSP - X"],
    "XSP-OL": ["GUDANG XSP-OL - X"],
    "HCW": ["SELLING AREA HCW - X", "TRANSIT HCW - X"],
    # "XSM GROW  - X" (spasi 2, sesuai nama di ERP) ikut ke XSM - laporan asli tdk py baris XSM Grow sendiri
    "XSM": ["GUDANG XSM - X", "SELLING AREA XSM - X", "TRANSIT XSM - X", "XSM GROW  - X"],
    "XMJ": ["GUDANG XMJ - X", "SELLING AREA XMJ - X", "TRANSIT XMJ - X"],
    "XWP": ["GUDANG XWP - X", "SELLING AREA XWP - X", "TRANSIT XWP - X"],
    "XPH": ["GUDANG XPH - X", "SELLING AREA XPH - X", "TRANSIT XPH - X"],
    "XTJ": ["GUDANG XTJ - X", "SELLING AREA XTJ - X", "TRANSIT XTJ - X"],
    "XCR": ["GUDANG XCR - X", "SELLING AREA XCR - X", "TRANSIT XCR - X"],
    "TASMU": ["GUDANG TASMU - X", "SELLING AREA TASMU - X", "TRANSIT TASMU - X"],
    "MNR": ["GUDANG MENARA - X", "SELLING AREA MENARA - X", "TRANSIT MENARA - X"],
    "UIN": ["GUDANG UIN - X", "SELLING AREA UIN - X", "TRANSIT UIN - X"],
    "KMT": ["GUDANG KEMITRAAN - X", "KEMITRAAN - X"],
    "MBG": ["MBG - X"],
    "XSL": ["SOCCERLITE - X"],
    "GD": ["GUDANG FHS - X", "Transit fhs  - X"],
    "DC": ["GUDANG DC - X"],
}

# Warehouse group yg SEMUA leaf di bawahnya (termasuk yg sudah disabled) ikut
# dihitung ke outlet tsb. XSM punya ratusan warehouse rak ("XSM 1 - X" dst, lalu
# rak baru "B1-CIGA - X" dst) di bawah AREA XSM - X. Rak lama di-disable &
# stoknya dipindah ke SELLING AREA XSM tgl 2026-10-09, tapi utk tanggal sebelum
# itu stok & penjualannya masih tercatat di rak - kalau tdk diikutkan, Saldo XSM
# 7/10/26 kurang Rp1,98 M & Penjualan kurang Rp19,5 jt. Sengaja pakai AREA XSM,
# bukan XSM - X, krn GUDANG DC - X juga ada di bawah XSM - X (baris sendiri).
_OUTLET_WAREHOUSE_GROUPS = {
    "XSM": ["AREA XSM - X"],
}


def _outlet_warehouses():
    """_OUTLET_WAREHOUSES + semua leaf warehouse di bawah _OUTLET_WAREHOUSE_GROUPS."""
    result = {code: list(whs) for code, whs in _OUTLET_WAREHOUSES.items()}
    for code, groups in _OUTLET_WAREHOUSE_GROUPS.items():
        for group in groups:
            bounds = frappe.db.get_value("Warehouse", group, ["lft", "rgt"], as_dict=True)
            if not bounds:
                continue
            leaves = frappe.db.sql_list("""
                SELECT name FROM `tabWarehouse`
                WHERE lft > %s AND rgt < %s AND is_group = 0
            """, (bounds.lft, bounds.rgt))
            result[code] += [wh for wh in leaves if wh not in result[code]]
    return result

_FASHION_ROWS = ["XSC", "XSC-OL", "PSR", "XPY", "XJB", "XCW", "OCW", "XSP", "XSP-OL", "HCW", "GD"]
_FMCG_ROWS = ["XSM", "XMJ", "XWP", "XPH", "XTJ", "XCR", "TASMU", "MNR", "UIN", "DC"]
_HO_ROWS = ["KMT", "MBG", "XSL"]

_OUTLET_LABELS = {
    "HCW": "X-sha Rumah Kedua", "MNR": "Menara", "UIN": "UIN Grow",
    "KMT": "KMT IPOS", "MBG": "MBG IPOS",
}

_VARIANTS = {
    "ALL": [],
    "EXC_TOPUP": ["TOPUP"],
    "EXC_TOPUP_SEM": ["TOPUP", "SEM"],
}


# PERFORMA (v2): data mentah diambil SEKALI per as_of_date utk semua varian
# (3 query, bukan 3 query x 3 varian), dikelompokkan per (warehouse, grp) dgn
# grp = item_group kalau termasuk grup yg bisa di-exclude (TOPUP/SEM), selain
# itu ''. Filter varian & pemetaan warehouse->outlet dikerjakan di Python.
# Query juga TIDAK membawa daftar warehouse (IN ratusan nama rak XSM) - cukup
# filter tanggal (index posting_date bawaan ERPNext), sisanya dibuang di Python.

def _grp_case(groups, params):
    if not groups:
        return "''"
    params += list(groups)
    return f"CASE WHEN i.item_group IN ({', '.join(['%s'] * len(groups))}) THEN i.item_group ELSE '' END"


def _fetch_inventory_raw(as_of_date, groups):
    """Return dict: balance {(wh, grp): val}, future {(wh, grp): val},
    mutasi {(wh, grp): {pembelian, penjualan, transfer_masuk, transfer_keluar, lainnya}}."""
    groups = sorted(set(groups or []))

    # Saldo SEKARANG dari tabBin. Bin dgn actual_qty = 0 dianggap bernilai 0:
    # stock_value di Bin bisa nyangkut kalau ada invoice yg di-cancel (contoh:
    # item 31385 di GUDANG OCW - qty 0 tapi stock_value -771.900 sejak 22/07/26),
    # laporan Excel asli tdk menghitungnya. Selain itu tetap pakai stock_value
    # (bukan qty * rate) krn sen-nya beda & laporan asli = stock_value (terbukti
    # dari pembulatan XPH).
    params = []
    grp = _grp_case(groups, params)
    balance = {
        (r.warehouse, r.grp): r.val or 0
        for r in frappe.db.sql(f"""
            SELECT b.warehouse, {grp} AS grp,
                   SUM(CASE WHEN b.actual_qty = 0 THEN 0 ELSE b.stock_value END) AS val
            FROM `tabBin` b
            JOIN `tabItem` i ON i.name = b.item_code
            GROUP BY b.warehouse, grp
        """, params, as_dict=True)
    }

    params = []
    grp = _grp_case(groups, params)
    params.append(as_of_date)
    future = {
        (r.warehouse, r.grp): r.val or 0
        for r in frappe.db.sql(f"""
            SELECT sle.warehouse, {grp} AS grp, SUM(sle.stock_value_difference) AS val
            FROM `tabStock Ledger Entry` sle
            JOIN `tabItem` i ON i.name = sle.item_code
            WHERE sle.is_cancelled = 0 AND sle.posting_date > %s
            GROUP BY sle.warehouse, grp
        """, params, as_dict=True)
    }

    # Mutasi HANYA tgl as_of_date. PENTING: pos/neg dijumlah TERPISAH per baris
    # SLE, bukan di-net dulu baru dicek tandanya. Kalau di-net dulu, warehouse
    # yg dalam 1 hari ada barang MASUK dan KELUAR sekaligus (2 Stock Entry
    # berbeda) akan salah hitung - Transfer Masuk/Keluar jadi separuh dari yang
    # sebenarnya (terbukti dari data: versi net menghasilkan Transfer Keluar FMCG
    # Rp33,8jt padahal seharusnya Rp39,7jt sesuai breakdown pos/neg mentah).
    params = []
    grp = _grp_case(groups, params)
    params.append(as_of_date)
    mutasi = {}
    for r in frappe.db.sql(f"""
        SELECT sle.warehouse, sle.voucher_type, {grp} AS grp,
               SUM(CASE WHEN sle.stock_value_difference >= 0 THEN sle.stock_value_difference ELSE 0 END) AS pos_val,
               SUM(CASE WHEN sle.stock_value_difference < 0 THEN sle.stock_value_difference ELSE 0 END) AS neg_val
        FROM `tabStock Ledger Entry` sle
        JOIN `tabItem` i ON i.name = sle.item_code
        WHERE sle.is_cancelled = 0 AND sle.posting_date = %s
        GROUP BY sle.warehouse, sle.voucher_type, grp
    """, params, as_dict=True):
        m = mutasi.setdefault((r.warehouse, r.grp), {"pembelian": 0, "penjualan": 0, "transfer_masuk": 0, "transfer_keluar": 0, "lainnya": 0})
        vt = r.voucher_type
        pos_val, neg_val = (r.pos_val or 0), (r.neg_val or 0)
        if vt in ("Purchase Invoice", "Purchase Receipt"):
            m["pembelian"] += pos_val
            m["lainnya"] += neg_val
        elif vt == "Sales Invoice":
            m["penjualan"] += pos_val + neg_val
        elif vt == "Stock Entry":
            m["transfer_masuk"] += pos_val
            m["transfer_keluar"] += abs(neg_val)
        else:
            m["lainnya"] += pos_val + neg_val

    return {"balance": balance, "future": future, "mutasi": mutasi}


def _kmt_mbg_inventory_row(kategori, as_of_date):
    """KMT & MBG tidak tercatat di sistem warehouse ERPNext sama sekali (sudah
    dibuktikan: tabBin kosong utk warehouse mereka) - datanya diambil dari
    doctype 'Kemitraan MBG Inventory History' (input manual dari laporan tim),
    sama spt pola yg dipakai utk data Sales KMT/MBG. Kalau blm ada record utk
    tanggal itu, kembalikan 0 (sama spt perilaku sebelumnya)."""
    row = frappe.db.get_value(
        "Kemitraan MBG Inventory History",
        {"kategori": kategori, "tanggal": as_of_date},
        ["saldo_awal", "pembelian", "penjualan", "transfer_masuk", "transfer_keluar", "lainnya", "saldo_akhir"],
        as_dict=True,
    )
    if not row:
        return {"saldo_awal": 0, "pembelian": 0, "penjualan": 0, "transfer_masuk": 0, "transfer_keluar": 0, "lainnya": 0, "saldo_akhir": 0}
    return {k: (v or 0) for k, v in row.items()}


_KMT_MBG_KATEGORI = {"KMT": "Kemitraan", "MBG": "MBG"}

_AMOUNT_KEYS = ("saldo_awal", "pembelian", "penjualan", "transfer_masuk", "transfer_keluar", "lainnya", "saldo_akhir")


def _rupiah(x):
    """Bulatkan ke rupiah persis spt laporan Excel asli: rapikan ke sen dulu
    (buang noise float), lalu ,50 sen ke BAWAH & >,50 ke atas. Divalidasi ke
    laporan 7/10/26: TOTAL saldo awal FMCG mentah 4.916.059.175,50 tertulis
    4.916.059.175 (ALL) & 4.840.353.326,50 -> 4.840.353.326 (EXC TOPUP);
    semua sel lain cocok dgn aturan ini."""
    sen = Decimal(repr(float(x or 0))).quantize(Decimal("0.01"), ROUND_HALF_UP)
    return int(sen.quantize(Decimal("1"), ROUND_HALF_DOWN))


def _build_variant(as_of_date, exclude_item_groups, raw=None, outlet_warehouses=None):
    exclude = set(exclude_item_groups or [])
    raw = raw or _fetch_inventory_raw(as_of_date, exclude)
    outlet_warehouses = outlet_warehouses or _outlet_warehouses()

    # ringkas data mentah per warehouse, buang grp yg di-exclude varian ini
    current_balance, future_movement, mutasi = {}, {}, {}
    for (wh, grp), val in raw["balance"].items():
        if grp not in exclude:
            current_balance[wh] = current_balance.get(wh, 0) + val
    for (wh, grp), val in raw["future"].items():
        if grp not in exclude:
            future_movement[wh] = future_movement.get(wh, 0) + val
    for (wh, grp), m in raw["mutasi"].items():
        if grp not in exclude:
            acc = mutasi.setdefault(wh, {k: 0 for k in m})
            for k, v in m.items():
                acc[k] += v

    def row_for(code):
        if code in _KMT_MBG_KATEGORI:
            r = _kmt_mbg_inventory_row(_KMT_MBG_KATEGORI[code], as_of_date)
            return {
                "outlet": code, "label": _OUTLET_LABELS.get(code, code),
                "saldo_awal": r["saldo_awal"],
                # "penjualan" disimpan positif (magnitude) di doctype sumbernya
                # (kolom "Keluar" laporan asli) - di-negatifkan di sini biar
                # konsisten dgn outlet lain (Fashion/FMCG selalu negatif).
                "pembelian": r["pembelian"], "penjualan": -r["penjualan"],
                "transfer_masuk": r["transfer_masuk"], "transfer_keluar": r["transfer_keluar"],
                "lainnya": abs(r["lainnya"]), "_lainnya_signed": r["lainnya"],
                "saldo_akhir": r["saldo_akhir"],
            }
        whs = outlet_warehouses[code]
        akhir = sum(current_balance.get(wh, 0) - future_movement.get(wh, 0) for wh in whs)
        m_total = {"pembelian": 0, "penjualan": 0, "transfer_masuk": 0, "transfer_keluar": 0, "lainnya": 0}
        for wh in whs:
            m = mutasi.get(wh, {})
            for k in m_total:
                m_total[k] += m.get(k, 0)
        net_hari_ini = (
            m_total["pembelian"] + m_total["penjualan"]
            + m_total["transfer_masuk"] - m_total["transfer_keluar"] + m_total["lainnya"]
        )
        awal = akhir - net_hari_ini
        return {
            "outlet": code, "label": _OUTLET_LABELS.get(code, code),
            "saldo_awal": awal,
            "pembelian": m_total["pembelian"], "penjualan": m_total["penjualan"],
            "transfer_masuk": m_total["transfer_masuk"], "transfer_keluar": m_total["transfer_keluar"],
            # kolom "Lainnya" di laporan Excel asli selalu ditampilkan positif (nilai
            # mutlak) walau transaksinya net rugi/berkurang secara akuntansi -
            # net_hari_ini tetap pakai nilai bertanda asli, cuma tampilannya di-abs().
            # _lainnya_signed disimpan utk dijumlah dulu (baris TOTAL) sebelum di-abs(),
            # supaya lainnya antar outlet yg tandanya beda saling menutupi dulu -
            # bukan menjumlahkan angka yg sudah positif semua.
            "lainnya": abs(m_total["lainnya"]), "_lainnya_signed": m_total["lainnya"],
            "saldo_akhir": akhir,
        }

    def section(rows, exclude_awal_from_total=None):
        exclude_awal_from_total = exclude_awal_from_total or set()
        data = [row_for(c) for c in rows]
        total = {"outlet": "TOTAL INVENTORY", "label": "TOTAL INVENTORY"}
        for k in ("pembelian", "penjualan", "transfer_masuk", "transfer_keluar", "saldo_akhir"):
            total[k] = sum(d[k] for d in data)
        # Saldo Awal KMT sengaja TIDAK diikutkan ke TOTAL (laporan Excel asli
        # blm py data historis KMT yg berkesinambungan waktu dibuat, jadi
        # TOTAL-nya dihitung tanpa KMT - baris KMT sendiri tetap tampil benar).
        total["saldo_awal"] = sum(
            d["saldo_awal"] for c, d in zip(rows, data) if c not in exclude_awal_from_total
        )
        total["lainnya"] = abs(sum(d["_lainnya_signed"] for d in data))
        for d in data:
            d.pop("_lainnya_signed", None)
        data.append(total)
        # Bulatkan ke rupiah SETELAH TOTAL dihitung dari nilai mentah (sama spt
        # laporan Excel asli: TOTAL = bulat(jumlah mentah), bukan jumlah baris
        # yg sudah dibulatkan - kalau dibalik, TOTAL bisa beda Rp1-2).
        for d in data:
            for k in _AMOUNT_KEYS:
                d[k] = _rupiah(d[k])
        return data

    return {
        "fashion": section(_FASHION_ROWS),
        "fmcg": section(_FMCG_ROWS),
        "ho": section(_HO_ROWS, exclude_awal_from_total={"KMT"}),
    }


@frappe.whitelist()
def get_daily_inventory(as_of_date=None):
    as_of_date = as_of_date or frappe.utils.today()
    all_groups = {g for groups in _VARIANTS.values() for g in groups}
    raw = _fetch_inventory_raw(as_of_date, all_groups)
    outlet_warehouses = _outlet_warehouses()
    return {
        "as_of_date": as_of_date,
        "variants": {
            variant_key: _build_variant(as_of_date, exclude_groups, raw, outlet_warehouses)
            for variant_key, exclude_groups in _VARIANTS.items()
        },
    }


_BULAN_ID_INV = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]


def _inv_target_by_outlet(bulan_label):
    # TARGET INV - input manual, blm ada master data (ad-hoc per bulan sesuai
    # arahan tim), diimport dari file "INV TARGET VS INV AKHIR AGT26" ke
    # doctype "Outlet Inventory Target". Bulan yg blm diinput -> None (jujur,
    # bukan 0/ditebak).
    rows = frappe.db.sql("""
        SELECT outlet, target_inv FROM `tabOutlet Inventory Target` WHERE bulan = %s
    """, (bulan_label,), as_dict=True)
    return {r["outlet"]: r["target_inv"] for r in rows}


# --- Monthly Inventory Target vs Inventory Akhir - All/Per Department/Per
# Outlet, EXCLUDE MBG/KMT/XSL (sesuai file referensi "INV TARGET VS INV AKHIR
# AGT26" sheet "EXC KMT, MBG, XSL"). "TOTAL INV" (Inventory Akhir) = reuse
# PERSIS mekanisme get_daily_inventory varian EXC_TOPUP (saldo_akhir) -
# divalidasi exact match ke file referensi utk Cikiray & Pasar.
@frappe.whitelist()
def get_monthly_inventory_target(department="FASHION", month=None, year=None):
    today = frappe.utils.getdate(frappe.utils.today())
    target_month = int(month) if month else today.month
    target_year = int(year) if year else today.year
    is_current_month = (target_year, target_month) == (today.year, today.month)
    if is_current_month:
        as_of_date = str(today)
    else:
        last_day = calendar.monthrange(target_year, target_month)[1]
        as_of_date = f"{target_year}-{target_month:02d}-{last_day:02d}"

    bulan_label = _BULAN_ID_INV[target_month - 1]
    targets = _inv_target_by_outlet(bulan_label)

    variant = _build_variant(as_of_date, ["TOPUP"])

    dept = department.upper()
    if dept == "FASHION":
        section_rows = variant["fashion"]
    elif dept == "FMCG":
        section_rows = variant["fmcg"]
    else:
        section_rows = variant["fashion"] + variant["fmcg"]

    rows = []
    total_inv, total_target = 0, 0
    for r in section_rows:
        if r["outlet"] == "TOTAL INVENTORY":
            continue
        target = targets.get(r["outlet"])
        total_inv_val = r["saldo_akhir"]
        row = {
            "outlet": r["outlet"], "label": r["label"],
            "target_inv": target, "total_inv": total_inv_val,
            "vs_target": (total_inv_val - target) if target is not None else None,
            "achv_pct": round(total_inv_val / target * 100, 2) if target else None,
        }
        rows.append(row)
        total_inv += total_inv_val
        total_target += target or 0

    rows.append({
        "outlet": "TOTAL", "label": "Total",
        "target_inv": total_target if total_target else None,
        "total_inv": total_inv,
        "vs_target": (total_inv - total_target) if total_target else None,
        "achv_pct": round(total_inv / total_target * 100, 2) if total_target else None,
    })

    return {
        "department": dept, "bulan": bulan_label, "tahun": target_year, "as_of_date": as_of_date,
        "rows": rows,
        "note": "Target inventory data manual (ad-hoc per bulan), blm ada master data. Bulan tanpa target -> null.",
    }
