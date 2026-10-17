# Copyright (c) 2026, X-SHA and contributors
# For license information, please see license.txt
#
# Sales YTD - tampilan ERP dari file admin "SALES X-SHA GROUP_YTD_ 2026"
# (1 sheet per outlet / departemen / TOTAL; baris Januari-Desember + kuartal;
# per tahun TARGET, SALES, ACH, GROWTH, kontribusi).
#
# Sumber angka per (kode sheet, tahun, bulan):
#  1. Sales YTD History (doctype) kalau ada - isinya:
#     - import sekali dari file YTD (2019 s/d CUTOVER Sept 2026, angka persis
#       file termasuk sheet total/departemen), lihat patch import_sales_ytd_history
#     - pembekuan otomatis tiap awal bulan (monthly_freeze_job): sales & target
#       bulan yg baru berakhir per outlet, supaya angka tdk berubah & target
#       tahun lalu tdk hilang (Sales Target Monthly di ERP cuma per nama bulan,
#       tanpa tahun -> tertimpa tiap tahun).
#  2. Bulan yg belum dibekukan (bulan berjalan) dihitung live per outlet:
#     SALES = "Penjualan" spt file SALES CLEAR (Sheet4 kolom Penjualan; file
#     YTD Agustus-Sept 2026 = persis angka ini), Kemitraan & MBG = input manual;
#     TARGET = Sales Target Monthly.
#  3. Sheet gabungan (DEPT / TOTAL / CIAWI ALL) yg tdk py angka tersimpan =
#     jumlah sheet komponennya (susunan = rumus file 2026).
# TOTAL2 & HO (INCLUDE XOL) di file tdk diisi lagi utk 2026 -> cuma histori.

import calendar
import json
import os

import frappe
from frappe.utils import getdate, today

_DATA = os.path.join(os.path.dirname(__file__), "custom_reports", "data", "sales_ytd_history.json")

# sheet file -> kode outlet ERP
LEAF = {
    "SLS & XMK": "KMT", "XSL": "XSL", "MBG": "MBG",
    "XSC": "XSC", "OSC": "XSC-OL", "PSR": "PSR", "XPY": "XPY", "XJB": "XJB", "XCW": "XCW", "OCW": "OCW",
    "XSP": "XSP", "OSP": "XSP-OL", "HCW": "HCW",
    "XSM": "XSM", "XMJ": "XMJ", "XWP": "XWP", "XPH": "XPH", "XTJ": "XTJ", "XCR": "XCR", "TASMU": "TASMU",
    "MENARA": "MNR", "GROW UIN": "UIN", "GROW SP": "XSMGROW",
}
_FHS = ["XSC", "OSC", "PSR", "XPY", "XJB", "XCW", "OCW", "XSP", "OSP", "HCW"]
_FMCG_EXC = ["XSM", "XMJ", "XWP", "XPH", "XTJ", "XCR", "TASMU", "MENARA", "GROW UIN", "GROW SP"]
AGG = {
    "CIAWI ALL": ["XCW", "OCW"],
    "DEPT.FHS": _FHS,
    "DEPT.FMCG": _FMCG_EXC + ["MBG"],
    "DEPT.FMCG excl MBG": _FMCG_EXC,
    "TOTAL": ["SLS & XMK", "XSL", "MBG", "DEPT.FHS", "DEPT.FMCG excl MBG"],
}
_MONTHS_EN = list(calendar.month_name)[1:]


def sheet_meta():
    """(urutan sheet, judul sheet) spt file."""
    with open(_DATA, encoding="utf-8") as f:
        d = json.load(f)
    titles = {k: (v or k) for k, v in d["titles"].items()}
    return d["order"], titles


class YTD:
    """Angka target & sales per (kode, tahun, bulan) - histori + live."""

    def __init__(self):
        self.stored = {}
        for r in frappe.get_all("Sales YTD History", fields=["kode", "tahun", "bulan", "target", "sales"], limit_page_length=0):
            self.stored[(r.kode, int(r.tahun), int(r.bulan))] = (r.target, r.sales)
        self.closed = {(y, m) for (_k, y, m) in self.stored}
        self.now = getdate(today())
        self._live = {}

    def live_month(self, year, month):
        """{kode outlet ERP: (target, sales)} bulan yg belum dibekukan (s/d hari ini)."""
        if (year, month) not in self._live:
            from custom_reports.custom_reports.report.monthly_sales_achievement_vs_target_net_retur_dan_potongan.monthly_sales_achievement_vs_target_net_retur_dan_potongan import (
                _Month, _period)
            cutoff = self.now.day if (year, month) == (self.now.year, self.now.month) else None
            start, end = _period(year, month, cutoff)
            mo = _Month(year, month, start, end, [])
            out = {}
            for code in set(LEAF.values()):
                d = mo.detail([code])
                out[code] = (d["target"], d["penjualan"])
            self._live[(year, month)] = out
        return self._live[(year, month)]

    def is_open(self, year, month):
        return (year, month) not in self.closed and (year, month) <= (self.now.year, self.now.month)

    def value(self, kode, year, month):
        """(target, sales) atau (None, None)."""
        if (kode, year, month) in self.stored:
            return self.stored[(kode, year, month)]
        if kode in AGG:
            parts = [self.value(k, year, month) for k in AGG[kode]]
            t = [p[0] for p in parts if p[0] is not None]
            s = [p[1] for p in parts if p[1] is not None]
            return (sum(t) if t else None, sum(s) if s else None)
        if kode in LEAF and self.is_open(year, month):
            t, s = self.live_month(year, month).get(LEAF[kode], (0, 0))
            return (t or None, s or None)
        return (None, None)

    def years(self, kode, upto):
        """Tahun yg ditampilkan utk sheet ini (spt file: tahun pertama yg ada datanya s/d upto)."""
        kodes = {kode}
        stack = list(AGG.get(kode, []))
        while stack:
            k = stack.pop()
            kodes.add(k)
            stack += AGG.get(k, [])
        ys = {y for (k, y, _m) in self.stored if k in kodes}
        if kode in LEAF or kode in AGG:
            ys.add(self.now.year)
        return sorted(y for y in ys if y <= upto)


def has_kontribusi(years, y):
    """Kolom kontribusi spt file: mulai 2023 & bukan tahun pertama sheet (kecuali sheet cuma 1 tahun)."""
    return len(years) == 1 or (y >= 2023 and y != years[0])


def build_sheet(ytd, kode, upto):
    """{years: [...], months: [{bulan, per tahun: target/sales/ach/growth/kontribusi}], quarters: [...], totals}."""
    years = ytd.years(kode, upto)
    grid = {y: [ytd.value(kode, y, m) for m in range(1, 13)] for y in years}

    def agg(y, ms):
        t = [grid[y][m - 1][0] for m in ms if grid[y][m - 1][0] is not None]
        s = [grid[y][m - 1][1] for m in ms if grid[y][m - 1][1] is not None]
        return (sum(t) if t else None, sum(s) if s else None)

    def cells(y, ms, year_total):
        t, s = agg(y, ms)
        prev = agg(y - 1, ms)[1] if (y - 1) in grid else None
        return {"target": t, "sales": s, "ach": (s / t * 100) if (s and t) else None,
                "growth": ((s - prev) / prev * 100) if (s is not None and prev) else None,
                "kontribusi": (s / year_total * 100) if (s is not None and year_total) else None}

    totals = {y: agg(y, range(1, 13))[1] for y in years}
    months = [{"label": _MONTHS_EN[m - 1], "per_year": {y: cells(y, [m], totals[y]) for y in years}} for m in range(1, 13)]
    total = {"label": "TOTAL", "per_year": {y: cells(y, range(1, 13), totals[y]) for y in years}}
    quarters = [{"label": f"Q{q}", "per_year": {y: cells(y, range(3 * q - 2, 3 * q + 1), totals[y]) for y in years}}
                for q in range(1, 5)]
    open_months = [(y, m) for y in years for m in range(1, 13) if ytd.is_open(y, m)]
    return {"years": years, "months": months, "total": total, "quarters": quarters, "open": open_months}


# ---------------------------------------------------------------------------
# import & pembekuan
def import_history():
    """Isi Sales YTD History dari file JSON (hasil olah file YTD admin). Idempoten."""
    with open(_DATA, encoding="utf-8") as f:
        d = json.load(f)
    have = {(r.kode, int(r.tahun), int(r.bulan)) for r in
            frappe.get_all("Sales YTD History", fields=["kode", "tahun", "bulan"], limit_page_length=0)}
    n = 0
    for r in d["rows"]:
        if (r["kode"], r["tahun"], r["bulan"]) in have:
            continue
        frappe.get_doc({"doctype": "Sales YTD History", "kode": r["kode"], "tahun": r["tahun"], "bulan": r["bulan"],
                        "target": r["target"], "sales": r["sales"], "sumber": "Import File YTD"}).insert(ignore_permissions=True)
        n += 1
    return n


def freeze_month(year, month, replace=False):
    """Simpan sales & target per outlet bulan itu (angka live ERP) ke Sales YTD History."""
    year, month = int(year), int(month)
    exists = frappe.get_all("Sales YTD History", filters={"tahun": year, "bulan": month}, pluck="name")
    if exists:
        imported = frappe.get_all("Sales YTD History", filters={"tahun": year, "bulan": month, "sumber": "Import File YTD"}, limit=1)
        if imported or not replace:
            return 0  # angka file admin tdk ditimpa
        for name in exists:
            frappe.delete_doc("Sales YTD History", name, ignore_permissions=True, force=True)
    ytd = YTD()
    ytd.closed.discard((year, month))
    live = ytd.live_month(year, month)
    n = 0
    for kode, code in LEAF.items():
        t, s = live.get(code, (0, 0))
        if not t and not s:
            continue
        frappe.get_doc({"doctype": "Sales YTD History", "kode": kode, "tahun": year, "bulan": month,
                        "target": t, "sales": s, "sumber": "ERP"}).insert(ignore_permissions=True)
        n += 1
    return n


def monthly_freeze_job():
    """Cron tgl 1: bekukan bulan yg baru berakhir."""
    first = getdate(today()).replace(day=1)
    prev = frappe.utils.add_days(first, -1)
    prev = getdate(prev)
    freeze_month(prev.year, prev.month)
    frappe.db.commit()


@frappe.whitelist()
def refreeze_month(tahun, bulan):
    """Hitung ulang angka bulan yg sudah dibekukan dari ERP (System Manager). Bulan hasil import file tdk diubah."""
    frappe.only_for("System Manager")
    n = freeze_month(tahun, bulan, replace=True)
    return {"rows": n}
