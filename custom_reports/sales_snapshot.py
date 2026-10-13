# Copyright (c) 2026, X-SHA and contributors
# For license information, please see license.txt
#
# Snapshot harian penjualan utk laporan "Daily Sales vs Target" - pola sama dgn
# inventory_snapshot.py. Yg dibekukan: TC & Sales harian per outlet dari Sales
# Invoice (rumus sama persis dgn sales_api._sales_by_outlet). Akumulasi bulan
# berjalan & MTD bulan lalu di laporan = jumlah snapshot harian, jadi angka
# tanggal yg sudah lewat tdk ikut berubah kalau ada invoice susulan/cancel.
#
# - Job tiap jam 00:00 (hooks.py) menyimpan snapshot hari yg BARU SAJA BERAKHIR.
# - Snapshot yg sudah ada TIDAK ditimpa job; koreksi sengaja lewat tombol
#   "Ambil Ulang Snapshot" di laporan (System Manager, tercatat di Version).
# - KMT & MBG TIDAK di-snapshot (input manual Kemitraan MBG Sales History),
#   target & data tahun lalu (Outlet Daily Sales History) jg tetap dibaca langsung.
# - API get_sales_vs_target / get_sales_vs_target_detail TIDAK diubah (live).

import frappe
from frappe.utils import add_days, getdate, now_datetime, today

from custom_reports.sales_api import _sales_by_outlet

_SNAPSHOT_DT = "Daily Sales Snapshot"
_ROW_DT = "Daily Sales Snapshot Row"


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
    sales = _sales_by_outlet(date, date)
    doc.snapshot_at = now_datetime()
    doc.sumber = sumber
    for outlet in sorted(o for o in sales if o):
        doc.append("rows", {"outlet": outlet, "tc": int(sales[outlet]["trx"] or 0),
                            "sales": round(sales[outlet]["sales"] or 0, 2)})
    doc.flags.ignore_permissions = True
    doc.save()
    return doc.name


def daily_snapshot_job():
    """Dijalankan scheduler jam 00:00 -> simpan snapshot hari yg baru berakhir."""
    save_snapshot(add_days(today(), -1))


@frappe.whitelist()
def retake_snapshot(date):
    """Tombol "Ambil Ulang Snapshot" di laporan Daily Sales vs Target."""
    frappe.only_for("System Manager")
    date = getdate(date)
    if date >= getdate(today()):
        frappe.throw("Snapshot hanya bisa diambil utk tanggal yg sudah berakhir (sebelum hari ini).")
    name = save_snapshot(date, overwrite=True, sumber=f"Ambil Ulang oleh {frappe.session.user}")
    return {"name": name, "snapshot_at": str(frappe.db.get_value(_SNAPSHOT_DT, name, "snapshot_at"))}


def load_sales(from_date, to_date):
    """{outlet: {"sales", "trx"}} - jumlah snapshot harian from_date..to_date,
    format sama dgn sales_api._sales_by_outlet. Return None kalau ADA tanggal
    di periode itu yg blm py snapshot (laporan lalu hitung live)."""
    from_date, to_date = getdate(from_date), getdate(to_date)
    n_days = (to_date - from_date).days + 1
    n_snap = frappe.db.sql(f"""
        SELECT COUNT(*) FROM `tab{_SNAPSHOT_DT}` WHERE tanggal BETWEEN %s AND %s
    """, (from_date, to_date))[0][0]
    if n_snap < n_days:
        return None
    rows = frappe.db.sql(f"""
        SELECT r.outlet, SUM(r.tc) AS trx, SUM(r.sales) AS sales
        FROM `tab{_ROW_DT}` r
        JOIN `tab{_SNAPSHOT_DT}` p ON p.name = r.parent AND r.parenttype = %s
        WHERE p.tanggal BETWEEN %s AND %s
        GROUP BY r.outlet
    """, (_SNAPSHOT_DT, from_date, to_date), as_dict=True)
    return {r.outlet: {"sales": r.sales or 0, "trx": r.trx or 0} for r in rows}
