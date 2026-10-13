# Copyright (c) 2026, X-SHA and contributors
# For license information, please see license.txt
#
# Snapshot harian Daily Inventory. Laporan "Daily Inventory" membaca angka yg
# SUDAH DIBEKUKAN di doctype "Daily Inventory Snapshot" (1 dokumen per tanggal),
# bukan hitung ulang live - supaya angka tanggal yg sudah lewat tdk ikut berubah
# kalau belakangan ada transaksi susulan/backdate/repost (contoh nyata: repost
# 9/10/26 bikin saldo XSM tgl 7/10 bergeser Rp3.850 dari laporan asli).
#
# - Job tiap jam 00:00 (hooks.py) menyimpan snapshot hari yg BARU SAJA BERAKHIR.
# - Snapshot yg sudah ada TIDAK ditimpa job; koreksi sengaja lewat tombol
#   "Ambil Ulang Snapshot" di laporan (System Manager, tercatat di Version).
# - Yg disimpan cuma outlet berbasis warehouse (Fashion, FMCG, XSL), nilai
#   MENTAH s.d. sen (lainnya bertanda) - pembulatan & TOTAL tetap dihitung saat
#   baca, jadi hasilnya identik dgn hitungan live. KMT & MBG TIDAK di-snapshot:
#   datanya input manual (Kemitraan MBG Inventory History) yg biasanya baru
#   diisi pagi harinya, & input manual itu sendiri sudah berupa angka tetap.
# - Tanggal yg blm py snapshot (hari ini, tgl sebelum fitur ini aktif) tetap
#   dihitung live - laporan memberi label "(live)".
# - API get_daily_inventory TIDAK diubah (tetap live).

import frappe
from frappe.utils import add_days, getdate, now_datetime, today

from custom_reports.inventory_api import (
    _VARIANTS,
    _fetch_inventory_raw,
    _outlet_raw_rows,
    _outlet_warehouses,
)

_SNAPSHOT_DT = "Daily Inventory Snapshot"
_ROW_DT = "Daily Inventory Snapshot Row"
_VALUE_KEYS = ("saldo_awal", "pembelian", "penjualan", "transfer_masuk", "transfer_keluar", "lainnya", "saldo_akhir")


def _compute_rows(date):
    """Baris snapshot (semua varian) utk 1 tanggal, dihitung live saat ini."""
    all_groups = {g for groups in _VARIANTS.values() for g in groups}
    raw = _fetch_inventory_raw(str(date), all_groups)
    outlet_warehouses = _outlet_warehouses()
    rows = []
    for variant_key, groups in _VARIANTS.items():
        for outlet, vals in _outlet_raw_rows(raw, set(groups), outlet_warehouses).items():
            row = {"varian": variant_key, "outlet": outlet}
            row.update({k: round(vals[k], 2) for k in _VALUE_KEYS})
            rows.append(row)
    return rows


def save_snapshot(date, overwrite=False, sumber="Job Otomatis"):
    """Simpan snapshot tgl `date`. Return nama dokumen. Kalau sudah ada & bukan
    overwrite, snapshot lama dibiarkan (angka tetap beku)."""
    date = str(getdate(date))
    if frappe.db.exists(_SNAPSHOT_DT, date):
        if not overwrite:
            return date
        doc = frappe.get_doc(_SNAPSHOT_DT, date)
        doc.set("rows", [])
    else:
        doc = frappe.new_doc(_SNAPSHOT_DT)
        doc.tanggal = date
    rows = _compute_rows(date)
    doc.snapshot_at = now_datetime()
    doc.sumber = sumber
    for row in rows:
        doc.append("rows", row)
    doc.flags.ignore_permissions = True
    doc.save()
    return doc.name


def daily_snapshot_job():
    """Dijalankan scheduler jam 00:00 -> simpan snapshot hari yg baru berakhir."""
    save_snapshot(add_days(today(), -1))


@frappe.whitelist()
def retake_snapshot(date):
    """Tombol "Ambil Ulang Snapshot" di laporan Daily Inventory."""
    frappe.only_for("System Manager")
    date = getdate(date)
    if date >= getdate(today()):
        frappe.throw("Snapshot hanya bisa diambil utk tanggal yg sudah berakhir (sebelum hari ini).")
    name = save_snapshot(date, overwrite=True, sumber=f"Ambil Ulang oleh {frappe.session.user}")
    return {"name": name, "snapshot_at": str(frappe.db.get_value(_SNAPSHOT_DT, name, "snapshot_at"))}


def load_outlet_rows(from_date, to_date, variant_key):
    """Gabungan snapshot periode from_date..to_date utk 1 varian, format sama dgn
    inventory_api._outlet_raw_rows: Saldo Awal = snapshot from_date, Saldo Akhir
    = snapshot to_date, mutasi = jumlah snapshot harian. Return None kalau ADA
    tanggal di periode itu yg blm py snapshot (laporan lalu hitung live)."""
    from_date, to_date = getdate(from_date), getdate(to_date)
    n_days = (to_date - from_date).days + 1
    rows = frappe.db.sql(f"""
        SELECT p.tanggal, r.outlet, {', '.join('r.' + k for k in _VALUE_KEYS)}
        FROM `tab{_ROW_DT}` r
        JOIN `tab{_SNAPSHOT_DT}` p ON p.name = r.parent AND r.parenttype = %s
        WHERE p.tanggal BETWEEN %s AND %s AND r.varian = %s
    """, (_SNAPSHOT_DT, from_date, to_date, variant_key), as_dict=True)
    if len({str(r.tanggal) for r in rows}) < n_days:
        return None

    out = {}
    for r in rows:
        acc = out.setdefault(r.outlet, {k: 0 for k in _VALUE_KEYS})
        for k in ("pembelian", "penjualan", "transfer_masuk", "transfer_keluar", "lainnya"):
            acc[k] += r[k] or 0
        if getdate(r.tanggal) == from_date:
            acc["saldo_awal"] = r.saldo_awal or 0
        if getdate(r.tanggal) == to_date:
            acc["saldo_akhir"] = r.saldo_akhir or 0
    return out
