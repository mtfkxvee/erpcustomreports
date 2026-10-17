# Copyright (c) 2026, X-SHA and contributors
# For license information, please see license.txt
#
# Laporan "Monthly Sales Achievement vs Target Net Retur dan Potongan" - tampilan ERP dari file admin "SALES
# CLEAR ACHV VS TARGET MoM YoY" (susunan baris mengikuti file):
#  - Tampilan "Ringkasan" = Sheet1: per periode (bulan ini / bulan lalu / tahun
#    lalu) TARGET, SALES ACHV, SALES VS TARGET + GROWTH vs bulan lalu & tahun lalu.
#  - Tampilan "Rincian" = Sheet4 (bagian bulan ini): Target, Penjualan, 4
#    potongan, SALES BRUTO 2, SALES TERLAPOR, RETUR, SALES - RETUR, SALES ACHV.
# Rumus = API sales_api.get_monthly_sales_net_achievement (_margin_row):
#   SALES BRUTO 2 = Penjualan - MEMBER - Potongan - Promo - Rafaksi (file J)
#   SALES - RETUR = SALES BRUTO 2 - Retur (file O)
#   SALES ACHV    = SALES - RETUR + Promo + Rafaksi (file P)
#   SALES VS TARGET = SALES ACHV / TARGET
#   GROWTH vs bulan lalu = (achv% bulan ini - achv% bulan lalu) / achv% bulan
#     lalu (file N: IFERROR((F-I)/I,0) - growth PENCAPAIAN, bukan growth sales)
# Keputusan (2026-10-16, rekomendasi yg disetujui "lanjutkan"):
#  - TARGET = Sales Target Monthly di ERP (file admin kadang beda, mis. Cikiray
#    Agustus ERP 2.350.000.293 vs file 2,5 M - admin perlu cek data target).
#  - Tahun lalu: ERP cuma py sales KOTOR histori (Outlet Daily Sales History),
#    tdk py target per tahun -> kolom target & achv% tahun lalu dikosongkan,
#    GROWTH vs tahun lalu = growth SALES (sales ini / sales tahun lalu - 1).
#  - Kemitraan & MBG = input manual Kemitraan MBG Sales History (tanpa potongan).
# Jurnal potongan & sales terlapor dibaca dari snapshot harian kalau bulan itu
# lengkap, kalau tidak live + label "(live)". Bulan berjalan dihitung s/d hari
# ini, bulan lalu dipotong di tanggal yg sama (MTD) spt API.

import calendar

import frappe
from frappe import _
from frappe.utils import getdate, today

from custom_reports.sales_api import (
    _BULAN_ID,
    _GL_MARGIN_ACCOUNTS,
    _OUTLET_COST_CENTER,
    _gl_deductions_by_outlet,
    _margin_row,
    _sales_by_kmt_mbg,
    _sales_by_outlet,
    _sales_by_outlet_history,
    _target_by_outlet,
)
from custom_reports.sales_snapshot import load_margin, load_sales

_TAMPILAN = ["Ringkasan", "Rincian"]
_FASHION_OFFLINE = [("XSC", "Cikiray", 1), ("PSR", "Pasar", 2), ("XPY", "Panyingkiran", 3), ("XJB", "Furniture", 4),
                    ("XCW", "Ciawi", 5), ("XSP", "SP Fashion", 6), ("HCW", "Ciawi Home Supplies", 7)]
_FASHION_ONLINE = [("XSC-OL", "Online Cikiray", None), ("OCW", "Online Ciawi", None), ("XSP-OL", "Online SP Fashion", None)]
_FMCG = [("XSM", "Supermart", 1), ("XMJ", "X-Shamart Mangunreja", 2), ("XWP", "X-Shamart Warung Peuteuy", 3),
         ("XPH", "X-Shamart Puspahiang", 4), ("XTJ", "X-Shamart Tanjung jaya", 5), ("XCR", "X-Shamart Cisaruni", 6),
         ("TASMU", "Tasmu Mart", 7), ("MNR", "Menara", 8), ("UIN", "X-sha Grow UIN", 9), ("XSMGROW", "X-sha Grow SP", 10)]
_HO = [("MBG", "MBG", None), ("KMT", "Kemitraan (inc sales xmk)", None), ("XSL", "Minisoccer", None)]
_MANUAL = ("KMT", "MBG")  # sales input manual, tanpa jurnal potongan
_DETAIL_KEYS = ("penjualan", "member", "potongan", "promo", "rafaksi", "sales_bruto_2", "sales_terlapor",
                "retur", "sales_retur", "sales_achv")


def _codes(items):
    return [c for c, _l, _n in items]


def _period(year, month, cutoff_day=None):
    days = calendar.monthrange(year, month)[1]
    end = min(cutoff_day, days) if cutoff_day else days
    return getdate(f"{year}-{month:02d}-01"), getdate(f"{year}-{month:02d}-{end:02d}")


class _Month:
    """Angka 1 bulan (bulan ini / bulan lalu): rincian per outlet + target."""

    def __init__(self, year, month, start, end, live_labels):
        outlets = [o for o in _OUTLET_COST_CENTER if o not in _MANUAL]
        snap = load_margin(start, end)
        self.gl = snap[0] if snap is not None else _gl_deductions_by_outlet(start, end, outlets)
        sales = load_sales(start, end)
        if snap is None or sales is None:
            live_labels.append(f"{_BULAN_ID[month - 1]} {year}")
        self.terlapor = sales if sales is not None else _sales_by_outlet(start, end)
        self.manual = _sales_by_kmt_mbg(start, end)
        self.targets = _target_by_outlet(_BULAN_ID[month - 1])

    def detail(self, codes):
        """Komponen Sheet4 utk sekumpulan outlet (dijumlah)."""
        si = [c for c in codes if c not in _MANUAL]
        m = _margin_row("x", "x", {acc: sum(self.gl.get(o, {}).get(acc, 0) or 0 for o in si) for acc in _GL_MARGIN_ACCOUNTS}, 0)
        d = {"penjualan": m["sales_bruto"], "member": m["member"], "potongan": m["potongan_penjualan"], "promo": m["promo"],
             "rafaksi": m["rafaksi_discount"], "sales_bruto_2": m["sales_bruto_2"], "retur": m["retur_penjualan"],
             "sales_retur": m["sales_retur"], "sales_achv": m["sales_achv"],
             "sales_terlapor": sum(self.terlapor.get(o, {}).get("sales", 0) or 0 for o in si)}
        for c in codes:
            if c in _MANUAL:
                s = self.manual.get(c, {}).get("sales", 0) or 0
                for k in ("penjualan", "sales_bruto_2", "sales_terlapor", "sales_retur", "sales_achv"):
                    d[k] += s
        d["target"] = sum(self.targets.get(c, 0) or 0 for c in codes)
        return d


def execute(filters=None):
    filters = filters or {}
    now = getdate(today())
    month = _BULAN_ID.index(filters.get("bulan")) + 1 if filters.get("bulan") in _BULAN_ID else now.month
    year = int(filters.get("tahun") or now.year)
    tampilan = filters.get("tampilan") or "Ringkasan"
    if tampilan not in _TAMPILAN:
        frappe.throw(_("Tampilan tidak dikenal: {0}").format(tampilan))

    cutoff = now.day if (year, month) == (now.year, now.month) else None
    m1, y1 = (month - 1, year) if month > 1 else (12, year - 1)
    start, end = _period(year, month, cutoff)
    lm_start, lm_end = _period(y1, m1, cutoff)
    ly_start, ly_end = _period(year - 1, month, cutoff)

    live = []
    cur = _Month(year, month, start, end, live)
    lm = _Month(y1, m1, lm_start, lm_end, live) if tampilan == "Ringkasan" else None
    if tampilan == "Ringkasan":
        ly_hist = _sales_by_outlet_history(ly_start, ly_end)
        ly_manual = _sales_by_kmt_mbg(ly_start, ly_end)

        def ly_sales(codes):
            return sum((ly_manual if c in _MANUAL else ly_hist).get(c, {}).get("sales", 0) or 0 for c in codes)

    def ringkasan_row(codes):
        c, p = cur.detail(codes), lm.detail(codes)
        achv = c["sales_achv"] / c["target"] if c["target"] else 0
        achv_lm = p["sales_achv"] / p["target"] if p["target"] else 0
        s_ly = ly_sales(codes)
        return {
            "target": c["target"], "sales_achv": c["sales_achv"], "achv": achv * 100,
            "target_lm": p["target"], "sales_achv_lm": p["sales_achv"], "achv_lm": achv_lm * 100,
            "sales_ly": s_ly,
            "growth_lm": ((achv - achv_lm) / achv_lm * 100) if achv_lm else 0,
            "growth_ly": ((c["sales_achv"] / s_ly - 1) * 100) if s_ly else 0,
        }

    def rincian_row(codes):
        d = cur.detail(codes)
        return {k: d[k] for k in ("target",) + _DETAIL_KEYS}

    build = ringkasan_row if tampilan == "Ringkasan" else rincian_row
    off, onl, fmcg, ho = _codes(_FASHION_OFFLINE), _codes(_FASHION_ONLINE), _codes(_FMCG), _codes(_HO)

    def row(label, codes, no=None, bold=0):
        r = build(codes)
        r.update({"no": no, "outlet": label, "bold": bold})
        return r

    data = [{"outlet": "1.FASHION & HOME.S", "bold": 1, "is_header": 1}]
    data += [row(lab, [c], no) for c, lab, no in _FASHION_OFFLINE]
    data.append(row("Total Outlet - Offline", off, bold=1))
    data += [row(lab, [c], no) for c, lab, no in _FASHION_ONLINE]
    data.append(row("Total Outlet - Online", onl, bold=1))
    data.append(row("Total Dept.F.H", off + onl, bold=1))
    data.append({"outlet": "2.FMCG", "bold": 1, "is_header": 1})
    data += [row(lab, [c], no) for c, lab, no in _FMCG]
    data.append(row("Total Dept.FMCG", fmcg, bold=1))
    data.append({"outlet": "3.HO", "bold": 1, "is_header": 1})
    data += [row(lab, [c], no) for c, lab, no in _HO]
    data.append(row("Total Dept.Holding", ho, bold=1))
    data.append(row("HO (Offline)", off + onl + fmcg + ho, bold=1))
    data.append(row("GRAND TOTAL", off + onl + fmcg + ho, bold=1))

    for r in data:
        for k, v in list(r.items()):
            if isinstance(v, float):
                r[k] = round(v, 2) if k in ("achv", "achv_lm", "growth_lm", "growth_ly") else round(v)

    info = f"{_BULAN_ID[month - 1]} {year}: tgl 1-{end.day}"
    if tampilan == "Ringkasan":
        info += f"  |  bulan lalu: {_BULAN_ID[m1 - 1]} {y1} tgl 1-{lm_end.day}  |  tahun lalu: sales kotor histori (tanpa target)"
    if live:
        info += f"  |  (live: {', '.join(live)})"
    data.insert(0, {"outlet": info, "bold": 1, "is_info": 1})
    cols = ringkasan_columns(month, year, m1, y1) if tampilan == "Ringkasan" else rincian_columns(month)
    return cols, data


def _col(fieldname, label, fieldtype="Int", width=130):
    return {"fieldname": fieldname, "label": label, "fieldtype": fieldtype, "width": width}


def _head():
    return [_col("no", _("No"), "Data", 45), _col("outlet", _("Department / Outlet"), "Data", 220)]


def ringkasan_columns(month, year, m1, y1):
    cur, lm, ly = f"{_BULAN_ID[month - 1]} {year}", f"{_BULAN_ID[m1 - 1]} {y1}", f"{_BULAN_ID[month - 1]} {year - 1}"
    return _head() + [
        _col("target", f"{cur} TARGET", width=140), _col("sales_achv", f"{cur} SALES ACHV", width=140),
        _col("achv", f"{cur} SALES VS TARGET", "Percent", 110),
        _col("target_lm", f"{lm} TARGET", width=140), _col("sales_achv_lm", f"{lm} SALES ACHV", width=140),
        _col("achv_lm", f"{lm} SALES VS TARGET", "Percent", 110),
        _col("sales_ly", f"{ly} SALES (kotor, histori)", width=150),
        _col("growth_lm", _("GROWTH VS LAST MONTH (pencapaian)"), "Percent", 130),
        _col("growth_ly", _("GROWTH VS LAST YEAR (sales)"), "Percent", 130),
    ]


def rincian_columns(month):
    bulan = _BULAN_ID[month - 1][:3].upper()
    return _head() + [
        _col("target", f"{bulan} Target", width=140), _col("penjualan", _("Penjualan"), width=140),
        _col("member", _("MEMBER-X")), _col("potongan", _("Potongan Penjualan")), _col("promo", _("Promo - X")),
        _col("rafaksi", _("RAFAKSI DISCOUNT - X")), _col("sales_bruto_2", _("SALES BRUTO 2"), width=140),
        _col("sales_terlapor", _("SALES TERLAPOR"), width=140), _col("retur", _("RETUR PENJUALAN")),
        _col("sales_retur", _("SALES - RETUR"), width=140), _col("sales_achv", _("SALES ACHV"), width=140),
    ]
