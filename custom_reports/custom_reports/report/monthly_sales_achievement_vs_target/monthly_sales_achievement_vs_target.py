# Copyright (c) 2026, X-SHA and contributors
# For license information, please see license.txt
#
# Laporan "Monthly Sales Achievement vs Target" (poin 1 Monthly Report: sales
# terlapor vs target, dikomparasikan dgn bulan & tahun sebelumnya) - file admin
# "SALES REPORT HO <BULAN>" sheet ALL / DEPT. F&H.S / DEPT. FMCG per tgl AKHIR
# BULAN. Isinya = persis report "Daily Sales vs Target" di tgl akhir bulan (MTD
# bulan lalu, MTD & monthly tahun lalu, 2026 vs 2025, balance) - tdk ada hitungan
# baru, report ini cuma memanggilnya dgn filter Bulan/Tahun supaya gampang dicari.
# Bulan berjalan -> s/d hari ini.

import calendar

from frappe.utils import getdate, today

from custom_reports.custom_reports.report.daily_sales_vs_target.daily_sales_vs_target import execute as _daily_execute
from custom_reports.sales_api import _BULAN_ID


def execute(filters=None):
    filters = filters or {}
    now = getdate(today())
    month = _BULAN_ID.index(filters.get("bulan")) + 1 if filters.get("bulan") in _BULAN_ID else now.month
    year = int(filters.get("tahun") or now.year)
    if (year, month) == (now.year, now.month):
        tanggal = now
    else:
        tanggal = getdate(f"{year}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}")
    return _daily_execute({"tanggal": str(tanggal), "departemen": filters.get("departemen") or "ALL"})
