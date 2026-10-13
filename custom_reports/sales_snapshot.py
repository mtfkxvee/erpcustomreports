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

from custom_reports.sales_api import (
    _OUTLET_COST_CENTER,
    _gl_deductions_by_outlet,
    _hpp_by_outlet,
    _sales_by_outlet,
)

_SNAPSHOT_DT = "Daily Sales Snapshot"
_ROW_DT = "Daily Sales Snapshot Row"
# Weekly Margin: akun GL (sama dgn sales_api._GL_MARGIN_ACCOUNTS) -> field snapshot.
# HPP juga dibekukan - repost item valuation terbukti menggeser HPP minggu lalu
# (mis. Supermart 5-11 Okt 2026: HPP ERP sekarang 264,5 jt vs file 266,6 jt).
_GL_FIELDS = {
    "Penjualan": "gl_penjualan",
    "Retur Penjualan": "gl_retur_penjualan",
    "MEMBER - X": "gl_member",
    "Potongan Penjualan": "gl_potongan_penjualan",
    "Promo - X": "gl_promo",
    "RAFAKSI DISCOUNT - X": "gl_rafaksi",
}
_MARGIN_OUTLETS = list(_OUTLET_COST_CENTER)


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
    gl = _gl_deductions_by_outlet(date, date, _MARGIN_OUTLETS)
    hpp = _hpp_by_outlet(date, date, _MARGIN_OUTLETS)
    doc.snapshot_at = now_datetime()
    doc.sumber = sumber
    for outlet in sorted(o for o in set(sales) | set(gl) | set(hpp) if o):
        row = {"outlet": outlet, "tc": int(sales.get(outlet, {}).get("trx") or 0),
               "sales": round(sales.get(outlet, {}).get("sales") or 0, 2),
               "hpp": round(hpp.get(outlet) or 0, 2)}
        for account, field in _GL_FIELDS.items():
            row[field] = round(gl.get(outlet, {}).get(account) or 0, 2)
        doc.append("rows", row)
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


def _complete(from_date, to_date):
    n_days = (to_date - from_date).days + 1
    n_snap = frappe.db.sql(f"""
        SELECT COUNT(*) FROM `tab{_SNAPSHOT_DT}` WHERE tanggal BETWEEN %s AND %s
    """, (from_date, to_date))[0][0]
    return n_snap >= n_days


def load_margin(from_date, to_date):
    """(gl_data, hpp_data) dari snapshot harian from_date..to_date, format sama
    dgn sales_api._gl_deductions_by_outlet & _hpp_by_outlet. None kalau ADA
    tanggal yg blm py snapshot (laporan lalu hitung live)."""
    from_date, to_date = getdate(from_date), getdate(to_date)
    if not _complete(from_date, to_date):
        return None
    sums = ", ".join(f"SUM(r.{f}) AS {f}" for f in _GL_FIELDS.values())
    rows = frappe.db.sql(f"""
        SELECT r.outlet, {sums}, SUM(r.hpp) AS hpp
        FROM `tab{_ROW_DT}` r
        JOIN `tab{_SNAPSHOT_DT}` p ON p.name = r.parent AND r.parenttype = %s
        WHERE p.tanggal BETWEEN %s AND %s
        GROUP BY r.outlet
    """, (_SNAPSHOT_DT, from_date, to_date), as_dict=True)
    gl_data = {r.outlet: {acc: r[f] or 0 for acc, f in _GL_FIELDS.items()} for r in rows}
    hpp_data = {r.outlet: r.hpp or 0 for r in rows}
    return gl_data, hpp_data


def load_sales(from_date, to_date):
    """{outlet: {"sales", "trx"}} - jumlah snapshot harian from_date..to_date,
    format sama dgn sales_api._sales_by_outlet. Return None kalau ADA tanggal
    di periode itu yg blm py snapshot (laporan lalu hitung live)."""
    from_date, to_date = getdate(from_date), getdate(to_date)
    if not _complete(from_date, to_date):
        return None
    rows = frappe.db.sql(f"""
        SELECT r.outlet, SUM(r.tc) AS trx, SUM(r.sales) AS sales
        FROM `tab{_ROW_DT}` r
        JOIN `tab{_SNAPSHOT_DT}` p ON p.name = r.parent AND r.parenttype = %s
        WHERE p.tanggal BETWEEN %s AND %s
        GROUP BY r.outlet
    """, (_SNAPSHOT_DT, from_date, to_date), as_dict=True)
    return {r.outlet: {"sales": r.sales or 0, "trx": r.trx or 0} for r in rows}
