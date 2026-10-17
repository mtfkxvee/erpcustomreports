# Copyright (c) 2026, X-SHA and contributors
# For license information, please see license.txt
#
# Laporan "Monthly Visitor TC AC Achievement vs Target" - tampilan ERP dari file admin
# "VISITOR, TC, AC ACHV VS TARGET, MoM YoY" sheet "EXC MBG,KMT,XSL" (susunan
# baris spt file; MBG/Kemitraan/Minisoccer tdk ikut, visitor toko fisik saja).
# Per periode (bulan ini / bulan lalu / tahun lalu): TARGET TC/AC/VISITOR,
# ACTUAL TC/AC/VISITOR, ACHV VS TARGET (= actual / target); lalu GROWTH spt
# tabel kanan file: pencapaian TC & AC bulan ini vs bulan lalu (file AL =
# IFERROR((AH-AK)/AK,0), growth PENCAPAIAN, bukan growth angka).
#  - TC & sales = Sales Invoice (sama dgn SALES REPORT HO), AC = sales / TC;
#    visitor = POS Closing Shift submitted.
#  - Target TC/AC = doctype "Outlet TC AC Target", target visitor = "Outlet
#    Visitor Target" (per nama bulan).
#  - Target AC baris total = target sales / target TC (rata2 tertimbang TC).
#    File tdk konsisten (Agustus diketik 149.393, Juli AVERAGE termasuk 0).
#  - Tahun lalu: ERP cuma py TC & sales histori (Outlet Daily Sales History),
#    tdk py target per tahun & visitor 2025 -> target tahun lalu dikosongkan,
#    growth vs tahun lalu = growth TC & AC aktual.
# TC & sales dari snapshot harian kalau bulan itu lengkap, kalau tidak live +
# label "(live)". Bulan berjalan s/d hari ini, pembanding dipotong tgl yg sama.

import frappe
from frappe import _
from frappe.utils import getdate, today

from custom_reports.custom_reports.report.monthly_sales_achievement_vs_target_net_retur_dan_potongan.monthly_sales_achievement_vs_target_net_retur_dan_potongan import _period
from custom_reports.sales_api import (
    _BULAN_ID,
    _sales_by_outlet,
    _sales_by_outlet_history,
    _target_tc_ac_by_outlet,
    _target_visitor_by_outlet,
    _visitor_by_outlet,
)
from custom_reports.sales_snapshot import load_sales

_FASHION = [("XSC", "Cikiray", 1), ("PSR", "Pasar", 2), ("XPY", "Panyingkiran", 3), ("XJB", "Furniture", 4),
            ("XCW", "Ciawi", 5), ("XSP", "SP Fashion", 6), ("HCW", "X-sha Rumah Kedua", 7),
            ("XSC-OL", "online cikiray", 8), ("OCW", "online ciawi", 9), ("XSP-OL", "online SP Fashion", 10)]
_FMCG = [("XSM", "Supermart", 1), ("XMJ", "X-Shamart Mangunreja", 2), ("XWP", "X-Shamart Warung peuteuy", 3),
         ("XPH", "X-Shamart Puspahiang", 4), ("XTJ", "X-Shamart Tanjung jaya", 5), ("XCR", "X-Shamart Cisaruni", 6),
         ("TASMU", "Tasmu Mart", 7), ("MNR", "Menara X-Shamart", 8), ("UIN", "UIN Grow", 9), ("XSMGROW", "XSM Grow", 10)]
_PCT = ("achv_tc", "achv_ac", "achv_visitor")


def _ratio(a, b):
    return a / b if b else 0


class _Period:
    """Aktual (+ target kalau ada) 1 periode."""

    def __init__(self, year, month, start, end, live, with_target=True, history=False):
        if history:
            self.sales, self.visitor = _sales_by_outlet_history(start, end), {}
        else:
            snap = load_sales(start, end)
            if snap is None:
                live.append(f"{_BULAN_ID[month - 1]} {year}")
            self.sales = snap if snap is not None else _sales_by_outlet(start, end)
            self.visitor = _visitor_by_outlet(start, end)
        bulan = _BULAN_ID[month - 1]
        self.t_tcac = _target_tc_ac_by_outlet(bulan) if with_target else {}
        self.t_vis = _target_visitor_by_outlet(bulan) if with_target else {}

    def values(self, codes):
        tc = sum(self.sales.get(o, {}).get("trx", 0) or 0 for o in codes)
        sales = sum(self.sales.get(o, {}).get("sales", 0) or 0 for o in codes)
        vis = sum(self.visitor.get(o, 0) or 0 for o in codes)
        t_tc = sum(self.t_tcac.get(o, {}).get("tc", 0) or 0 for o in codes)
        t_sales = sum((self.t_tcac.get(o, {}).get("tc", 0) or 0) * (self.t_tcac.get(o, {}).get("ac", 0) or 0) for o in codes)
        if len(codes) == 1:
            t_ac = self.t_tcac.get(codes[0], {}).get("ac", 0) or 0
        else:
            t_ac = _ratio(t_sales, t_tc)
        t_vis = sum(self.t_vis.get(o, 0) or 0 for o in codes)
        ac = _ratio(sales, tc)
        return {"t_tc": t_tc, "t_ac": t_ac, "t_visitor": t_vis, "tc": tc, "ac": ac, "visitor": vis,
                "achv_tc": _ratio(tc, t_tc) * 100, "achv_ac": _ratio(ac, t_ac) * 100, "achv_visitor": _ratio(vis, t_vis) * 100}


def execute(filters=None):
    filters = filters or {}
    now = getdate(today())
    month = _BULAN_ID.index(filters.get("bulan")) + 1 if filters.get("bulan") in _BULAN_ID else now.month
    year = int(filters.get("tahun") or now.year)
    cutoff = now.day if (year, month) == (now.year, now.month) else None
    m1, y1 = (month - 1, year) if month > 1 else (12, year - 1)

    live = []
    cur = _Period(year, month, *_period(year, month, cutoff), live)
    lm = _Period(y1, m1, *_period(y1, m1, cutoff), live)
    ly = _Period(year - 1, month, *_period(year - 1, month, cutoff), live, with_target=False, history=True)
    end = _period(year, month, cutoff)[1]

    def row(label, codes, no=None, bold=0):
        r = {"no": no, "outlet": label, "bold": bold}
        c, p, y = cur.values(codes), lm.values(codes), ly.values(codes)
        r.update(c)
        r.update({f"lm_{k}": v for k, v in p.items()})
        r.update({"ly_tc": y["tc"], "ly_ac": y["ac"]})
        r["g_tc_lm"] = _ratio(c["achv_tc"] - p["achv_tc"], p["achv_tc"]) * 100
        r["g_ac_lm"] = _ratio(c["achv_ac"] - p["achv_ac"], p["achv_ac"]) * 100
        r["g_tc_ly"] = (_ratio(c["tc"], y["tc"]) - 1) * 100 if y["tc"] else 0
        r["g_ac_ly"] = (_ratio(c["ac"], y["ac"]) - 1) * 100 if y["ac"] else 0
        return r

    data = [{"outlet": "FASHION & H S", "bold": 1, "is_header": 1}]
    data += [row(lab, [c], no) for c, lab, no in _FASHION]
    data.append(row("FASHION & H S", [c for c, _l, _n in _FASHION], bold=1))
    data.append({"outlet": "FMCG", "bold": 1, "is_header": 1})
    data += [row(lab, [c], no) for c, lab, no in _FMCG]
    data.append(row("FMCG", [c for c, _l, _n in _FMCG], bold=1))

    for r in data:
        for k, v in list(r.items()):
            if isinstance(v, float):
                r[k] = round(v, 2) if (k.startswith(("achv", "lm_achv", "g_"))) else round(v)

    info = (f"{_BULAN_ID[month - 1]} {year} tgl 1-{end.day}  |  bulan lalu {_BULAN_ID[m1 - 1]} {y1}  |  "
            f"tahun lalu: TC & AC histori (tanpa target & visitor)  |  EXC MBG, KMT, XSL")
    if live:
        info += f"  |  (live: {', '.join(live)})"
    data.insert(0, {"outlet": info, "bold": 1, "is_info": 1})
    return get_columns(month, year, m1, y1), data


def _col(fieldname, label, fieldtype="Int", width=110):
    return {"fieldname": fieldname, "label": label, "fieldtype": fieldtype, "width": width}


def get_columns(month, year, m1, y1):
    cur, lm, ly = f"{_BULAN_ID[month - 1][:3]} {year}", f"{_BULAN_ID[m1 - 1][:3]} {y1}", f"{_BULAN_ID[month - 1][:3]} {year - 1}"
    cols = [_col("no", _("No"), "Data", 45), _col("outlet", _("Outlet"), "Data", 200)]
    for pre, lab in (("", cur), ("lm_", lm)):
        cols += [_col(f"{pre}t_tc", f"{lab} Target TC"), _col(f"{pre}t_ac", f"{lab} Target AC"), _col(f"{pre}t_visitor", f"{lab} Target Visitor"),
                 _col(f"{pre}tc", f"{lab} TC"), _col(f"{pre}ac", f"{lab} AC"), _col(f"{pre}visitor", f"{lab} Visitor"),
                 _col(f"{pre}achv_tc", f"{lab} Achv TC", "Percent"), _col(f"{pre}achv_ac", f"{lab} Achv AC", "Percent"),
                 _col(f"{pre}achv_visitor", f"{lab} Achv Visitor", "Percent")]
    cols += [_col("ly_tc", f"{ly} TC (histori)"), _col("ly_ac", f"{ly} AC (histori)"),
             _col("g_tc_lm", _("Growth Achv TC vs Bln Lalu"), "Percent", 130), _col("g_ac_lm", _("Growth Achv AC vs Bln Lalu"), "Percent", 130),
             _col("g_tc_ly", _("Growth TC vs Thn Lalu"), "Percent", 120), _col("g_ac_ly", _("Growth AC vs Thn Lalu"), "Percent", 120)]
    return cols
