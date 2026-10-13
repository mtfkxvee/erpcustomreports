# Copyright (c) 2026, X-SHA and contributors
# For license information, please see license.txt
#
# Laporan "Weekly Visitor TC AC Achievement" - tampilan ERP dari file "SALES
# REPORT HO" sheet "Data weekly" bagian kiri: per minggu (blok tgl 1-7 / 8-14 /
# 15-21 / 22-akhir bulan) TC, Sales, AC, VISITOR + Growth vs minggu sebelumnya
# + MTD, per outlet & total (FASHION & H S / FMCG / HOLDING).
# Admin biasa membuat laporan ini terpisah, jadi dibuat sbg report sendiri -
# tapi perhitungannya SAMA PERSIS dgn tampilan "Mingguan" report Weekly Sales
# Achievement (dipanggil langsung, bukan disalin), supaya kedua laporan tdk
# pernah beda angka. Visitor = POS Closing Shift yg submitted
# (sales_api._visitor_by_outlet); TC & Sales dari snapshot penjualan harian.

from custom_reports.custom_reports.report.weekly_sales_achievement.weekly_sales_achievement import (
    execute as _weekly_execute,
)


def execute(filters=None):
    filters = dict(filters or {})
    filters["tampilan"] = "Mingguan"
    return _weekly_execute(filters)
