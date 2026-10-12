# Copyright (c) 2026, X-SHA and contributors
# For license information, please see license.txt
#
# Laporan "Daily Inventory" (Saldo Awal/Pembelian/Penjualan/Transfer Masuk/
# Transfer Keluar/Lainnya/Saldo Akhir per outlet) - tampilan ERP dari API
# custom_reports.inventory_api.get_daily_inventory, pakai perhitungan yg SAMA
# (_build_variant) supaya angka laporan & API selalu identik. Dari = Sampai
# -> laporan harian (persis laporan Excel); periode -> Saldo Awal di awal
# Dari Tanggal, mutasi = jumlah selama periode, Saldo Akhir di akhir Sampai Tanggal.

import frappe
from frappe import _
from frappe.utils import formatdate, getdate, today

from custom_reports.inventory_api import (
    _AMOUNT_KEYS,
    _FASHION_ROWS,
    _FMCG_ROWS,
    _HO_ROWS,
    _VARIANTS,
    _build_variant,
    _fetch_inventory_raw,
)

_VARIANT_BY_LABEL = {
    "ALL": "ALL",
    "EXC TOPUP": "EXC_TOPUP",
    "EXC TOPUP&SEM": "EXC_TOPUP_SEM",
}

_SECTIONS = [
    ("fashion", "INVENTORY FASHION", _FASHION_ROWS),
    ("fmcg", "INVENTORY FMCG", _FMCG_ROWS),
    ("ho", "INVENTORY HO", _HO_ROWS),
]


def execute(filters=None):
    filters = filters or {}
    from_date = getdate(filters.get("from_date") or today())
    to_date = getdate(filters.get("to_date") or today())
    if from_date > to_date:
        frappe.throw(_("Dari Tanggal tidak boleh setelah Sampai Tanggal."))
    variant_key = _VARIANT_BY_LABEL.get(filters.get("variant") or "ALL", "ALL")
    groups = _VARIANTS[variant_key]

    raw = _fetch_inventory_raw(str(to_date), groups, str(from_date))
    variant = _build_variant(str(to_date), groups, raw, None, str(from_date))

    if from_date == to_date:
        period_label = formatdate(to_date, "dd/MM/yy")
    else:
        period_label = f"{formatdate(from_date, 'dd/MM/yy')} - {formatdate(to_date, 'dd/MM/yy')}"

    data = []
    for key, title, _rows in _SECTIONS:
        data.append({"outlet": f"{title} {period_label}", "is_header": 1, "bold": 1})
        for row in variant[key]:
            is_total = row["outlet"] == "TOTAL INVENTORY"
            out = {"outlet": "TOTAL INVENTORY" if is_total else row["label"], "bold": 1 if is_total else 0}
            for k in _AMOUNT_KEYS:
                out[k] = row[k]
            data.append(out)
        data.append({})

    return get_columns(), data[:-1]


def get_columns():
    cols = [{"fieldname": "outlet", "label": _("Outlet"), "fieldtype": "Data", "width": 260}]
    labels = {
        "saldo_awal": _("Saldo Awal"), "pembelian": _("Pembelian"), "penjualan": _("Penjualan"),
        "transfer_masuk": _("Transfer Masuk"), "transfer_keluar": _("Transfer Keluar"),
        "lainnya": _("Lainnya"), "saldo_akhir": _("Saldo Akhir"),
    }
    for k in _AMOUNT_KEYS:
        cols.append({"fieldname": k, "label": labels[k], "fieldtype": "Int", "width": 150})
    return cols
