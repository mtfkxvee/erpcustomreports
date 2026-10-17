# Copyright (c) 2026, X-SHA and contributors
# For license information, please see license.txt
#
# Laporan "Weekly Sales Achievement Net Retur dan Potongan" (dulu "Weekly Sales Net
# Achievement") = rincian perhitungan
# Weekly Margin - tampilan ERP dari file admin "WEEKLY MARGIN CLEAR 28-4 SEPT"
# Sheet4 (susunan kolom & baris mengikuti file). Admin: file ini "untuk
# perhitungan", hasilnya disalin ke laporan WEEKLY MARGIN OCTOBER (= report
# Weekly Margin). Poin 2 daftar laporan (sales setelah retur & potongan) =
# kolom SALES - RETUR & SALES ACHV di sini. Rumus (file Sheet4):
#   SALES BRUTO 2 = Penjualan - MEMBER - Potongan - Promo - Rafaksi (J)
#   SALES - RETUR = SALES BRUTO 2 - RETUR (O)
#   SALES ACHV    = SALES - RETUR + Promo + Rafaksi (P)
#   HPP - RETUR   = HPP - RETUR HPP (Q; RETUR HPP di file kosong = 0)
#   deal margin clear = SALES - RETUR - HPP - RETUR (R), % = R / O (S)
#   deal margin ++    = SALES ACHV - HPP - RETUR (T)
# Minggu = Senin-Minggu. Jurnal potongan, HPP & sales terlapor dari snapshot
# harian kalau lengkap, kalau tidak live + label "(live)". MBG & Kemitraan =
# input manual (Kemitraan MBG Sales History: sales + HPP); HPP blm diinput ->
# margin baris itu kosong. Spt file: baris "Kemitraan (inc sales xmk)" di tabel
# = 0, sales & margin Kemitraan ditulis terpisah di bawah GRAND TOTAL ("kmt"),
# lalu baris total termasuk kmt.

import frappe
from frappe import _
from frappe.utils import formatdate, getdate, today

from custom_reports.custom_reports.report.weekly_margin_target_vs_achievement.weekly_margin_target_vs_achievement import _kmt_mbg_sales_hpp
from custom_reports.sales_api import (
    _GL_MARGIN_ACCOUNTS,
    _OUTLET_COST_CENTER,
    _gl_deductions_by_outlet,
    _hpp_by_outlet,
    _margin_row,
    _monday_week_bounds,
    _sales_by_outlet,
)
from custom_reports.sales_snapshot import load_margin, load_sales

_FASHION_OFFLINE = [("XSC", "Cikiray", 1), ("PSR", "Pasar", 2), ("XPY", "Panyingkiran", 3), ("XJB", "Furniture", 4),
                    ("XCW", "Ciawi", 5), ("XSP", "SP Fashion", 6), ("HCW", "Ciawi Home Supplies", 7)]
_FASHION_ONLINE = [("XSC-OL", "Online Cikiray", None), ("OCW", "Online Ciawi", None), ("XSP-OL", "Online SP Fashion", None)]
_FMCG = [("XSM", "Supermart", 1), ("XMJ", "X-Shamart Mangunreja", 2), ("XWP", "X-Shamart Warung Peuteuy", 3),
         ("XPH", "X-Shamart Puspahiang", 4), ("XTJ", "X-Shamart Tanjung jaya", 5), ("XCR", "X-Shamart Cisaruni", 6),
         ("TASMU", "Tasmu Mart", 7), ("MNR", "Menara", 8), ("UIN", "X-sha Grow UIN", 9), ("XSMGROW", "X-sha Grow SP", 10)]
_MANUAL = ("KMT", "MBG")
_MONEY = ("penjualan", "member", "potongan", "promo", "rafaksi", "sales_bruto_2", "sales_terlapor", "hpp", "retur",
          "retur_hpp", "sales_retur", "sales_achv", "hpp_retur", "deal_margin_clear", "deal_margin")


def _codes(items):
    return [c for c, _l, _n in items]


def execute(filters=None):
    filters = filters or {}
    as_of = getdate(filters.get("tanggal") or today())
    ws, we = (getdate(d) for d in _monday_week_bounds(as_of))

    si_outlets = [o for o in _OUTLET_COST_CENTER if o not in _MANUAL]
    snap = load_margin(ws, we)
    gl, hpp = snap if snap is not None else (_gl_deductions_by_outlet(ws, we, si_outlets), _hpp_by_outlet(ws, we, si_outlets))
    sales_snap = load_sales(ws, we)
    terlapor = sales_snap if sales_snap is not None else _sales_by_outlet(ws, we)
    is_live = snap is None or sales_snap is None
    manual = _kmt_mbg_sales_hpp(ws, we)

    def calc(codes):
        si = [c for c in codes if c not in _MANUAL]
        m = _margin_row("x", "x", {acc: sum(gl.get(o, {}).get(acc, 0) or 0 for o in si) for acc in _GL_MARGIN_ACCOUNTS},
                        sum(hpp.get(o, 0) or 0 for o in si))
        d = {"penjualan": m["sales_bruto"], "member": m["member"], "potongan": m["potongan_penjualan"], "promo": m["promo"],
             "rafaksi": m["rafaksi_discount"], "sales_bruto_2": m["sales_bruto_2"], "retur": m["retur_penjualan"],
             "sales_retur": m["sales_retur"], "sales_achv": m["sales_achv"], "hpp": m["hpp"], "retur_hpp": 0,
             "sales_terlapor": sum(terlapor.get(o, {}).get("sales", 0) or 0 for o in si)}
        margin_ok = bool(si)
        no_hpp_sales = 0  # sales KMT/MBG yg HPP-nya blm diinput -> tdk ikut hitungan margin
        for c in codes:
            if c not in _MANUAL:
                continue
            x = manual.get(c, {"sales": 0, "hpp": 0, "hpp_filled": False})
            for k in ("penjualan", "sales_bruto_2", "sales_terlapor", "sales_retur", "sales_achv"):
                d[k] += x["sales"]
            if x["hpp_filled"]:
                d["hpp"] += x["hpp"]
                margin_ok = True
            else:
                no_hpp_sales += x["sales"]
        d["hpp_retur"] = d["hpp"] - d["retur_hpp"]
        if margin_ok:
            base_retur, base_achv = d["sales_retur"] - no_hpp_sales, d["sales_achv"] - no_hpp_sales
            d["deal_margin_clear"] = base_retur - d["hpp_retur"]
            d["margin_pct"] = d["deal_margin_clear"] / base_retur * 100 if base_retur else 0
            d["deal_margin"] = base_achv - d["hpp_retur"]
        else:
            d.update({"hpp": None, "hpp_retur": None, "deal_margin_clear": None, "margin_pct": None, "deal_margin": None})
        return d

    def row(label, codes, no=None, bold=0):
        r = calc(codes)
        r.update({"no": no, "outlet": label, "bold": bold})
        return r

    off, onl, fmcg = _codes(_FASHION_OFFLINE), _codes(_FASHION_ONLINE), _codes(_FMCG)
    ho = ["MBG", "XSL"]  # spt file: Kemitraan TIDAK masuk tabel & total (ditulis terpisah di bawah)
    data = [{"outlet": "1.FASHION & HOME.S", "bold": 1, "is_header": 1}]
    data += [row(lab, [c], no) for c, lab, no in _FASHION_OFFLINE]
    data.append(row("Total Outlet - Offline", off, bold=1))
    data += [row(lab, [c], no) for c, lab, no in _FASHION_ONLINE]
    data.append(row("Total Outlet - Online", onl, bold=1))
    data.append(row("Total Dept.F.H", off + onl, bold=1))
    data.append({"outlet": "2.FMCG", "bold": 1, "is_header": 1})
    data += [row(lab, [c], no) for c, lab, no in _FMCG]
    data.append(row("Total Dept.FMCG", fmcg, bold=1))
    data.append({"outlet": "4.HO", "bold": 1, "is_header": 1})
    data += [row("MBG", ["MBG"]), row("Kemitraan (inc sales xmk)", []), row("Minisoccer", ["XSL"])]
    data.append(row("Total Dept.Holding", ho, bold=1))
    data.append(row("HO (Offline)", off + onl + fmcg + ho, bold=1))
    data.append(row("GRAND TOTAL", off + onl + fmcg + ho, bold=1))
    data.append({})
    data.append(row("kmt (Kemitraan, sales terlapor berbeda)", ["KMT"]))
    data.append(row("GRAND TOTAL + kmt", off + onl + fmcg + ho + ["KMT"], bold=1))

    for r in data:
        for k in _MONEY:
            if isinstance(r.get(k), float):
                r[k] = round(r[k])
        if isinstance(r.get("margin_pct"), float):
            r["margin_pct"] = round(r["margin_pct"], 2)

    info = f"Minggu: {formatdate(ws, 'dd')}-{formatdate(we, 'dd MMMM yyyy')} (Senin-Minggu)"
    no_hpp = [n for c, n in (("MBG", "MBG"), ("KMT", "Kemitraan")) if not manual.get(c, {}).get("hpp_filled")]
    if no_hpp:
        info += f"  |  HPP {', '.join(no_hpp)} blm diinput -> margin kosong & tdk ikut margin total"
    if is_live:
        info += "  |  (live)"
    data.insert(0, {"outlet": info, "bold": 1, "is_info": 1})
    return get_columns(), data


def get_columns():
    def col(fieldname, label, fieldtype="Int", width=130):
        return {"fieldname": fieldname, "label": label, "fieldtype": fieldtype, "width": width}
    return [
        col("no", _("No"), "Data", 45),
        col("outlet", _("Department / Outlet"), "Data", 230),
        col("penjualan", _("Penjualan"), width=140), col("member", _("MEMBER-X")),
        col("potongan", _("Potongan Penjualan")), col("promo", _("Promo - X")), col("rafaksi", _("RAFAKSI DISCOUNT - X")),
        col("sales_bruto_2", _("SALES BRUTO 2"), width=140), col("sales_terlapor", _("SALES TERLAPOR"), width=140),
        col("hpp", _("HPP ERP"), width=140), col("retur", _("RETUR PENJUALAN")), col("retur_hpp", _("RETUR HPP")),
        col("sales_retur", _("SALES - RETUR"), width=140), col("sales_achv", _("SALES ACHV"), width=140),
        col("hpp_retur", _("HPP - RETUR"), width=140), col("deal_margin_clear", _("deal margin clear"), width=140),
        col("margin_pct", _("%"), "Percent", 90), col("deal_margin", _("deal margin ++"), width=140),
    ]
