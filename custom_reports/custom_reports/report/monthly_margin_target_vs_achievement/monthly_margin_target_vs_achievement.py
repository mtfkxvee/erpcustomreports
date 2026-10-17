# Copyright (c) 2026, X-SHA and contributors
# For license information, please see license.txt
#
# Laporan "Monthly Margin Target vs Achievement" - tampilan ERP dari file admin "SALES & MARGIN ACHV
# AGUSTUS 2026" (susunan baris spt file, sama dgn Monthly Sales Net Achievement):
#  - Tampilan "Ringkasan" = Sheet1: TARGET SALES, SALES ACHV, ACHV VS TARGET,
#    DEAL MARGIN, TARGET MARGIN %, MARGIN ACHV %, ACHV VS TARGET, TARGET MARGIN
#    RP, MARGIN ACHV RP.
#  - Tampilan "Rincian" = Sheet4: Penjualan s/d SALES ACHV + HPP, deal margin.
# Rumus (file):
#   SALES ACHV       = SALES - RETUR + Promo + Rafaksi (P = O + H + I)
#   DEAL MARGIN      = SALES ACHV - HPP (Sheet4 T = P - Q, "deal margin ++")
#   deal margin clear= SALES - RETUR - HPP (R = O - Q), % = R / O
#   MARGIN ACHV %    = DEAL MARGIN / SALES ACHV (J = H / E)
#   ACHV VS TARGET   = MARGIN ACHV % / TARGET MARGIN % (K = J / I)
#   TARGET MARGIN RP = TARGET MARGIN % x TARGET SALES (M = I x D)
#   MARGIN ACHV RP   = DEAL MARGIN - TARGET MARGIN RP (N = H - M)
# Target margin: per outlet sales_api._MARGIN_TARGET_PCT, Total Offline 24%,
# Online 22%, dept 24%/16%, Holding & GRAND TOTAL = target HO bulan itu (4
# desimal spt file: Agustus 0,208). Target sales = Sales Target Monthly ERP.
# Kemitraan & MBG: sales + HPP input manual (Kemitraan MBG Sales History, field
# HPP). HPP blm diinput -> margin baris itu kosong & tdk ikut hitungan margin
# total (sales-nya tetap ikut SALES ACHV), dicatat di baris info.
# Jurnal potongan, HPP & sales terlapor dari snapshot harian kalau lengkap,
# kalau tidak live + label "(live)".

import frappe
from frappe import _
from frappe.utils import getdate, today

from custom_reports.custom_reports.report.monthly_sales_achievement_vs_target_net_retur_dan_potongan.monthly_sales_achievement_vs_target_net_retur_dan_potongan import (
    _FASHION_OFFLINE,
    _FASHION_ONLINE,
    _FMCG,
    _HO,
    _MANUAL,
    _codes,
    _period,
)
from custom_reports.custom_reports.report.weekly_margin_target_vs_achievement.weekly_margin_target_vs_achievement import (
    _OFFLINE_TARGET,
    _ONLINE_TARGET,
    _ho_target,
    _kmt_mbg_sales_hpp,
)
from custom_reports.sales_api import (
    _BULAN_ID,
    _GL_MARGIN_ACCOUNTS,
    _MARGIN_DEPT_TARGET_PCT,
    _MARGIN_TARGET_PCT,
    _OUTLET_COST_CENTER,
    _gl_deductions_by_outlet,
    _hpp_by_outlet,
    _margin_row,
    _sales_by_outlet,
    _target_by_outlet,
)
from custom_reports.sales_snapshot import load_margin, load_sales

_TAMPILAN = ["Ringkasan", "Rincian"]
_PCT_KEYS = ("achv", "target_margin_pct", "margin_achv_pct", "achv_margin", "margin_pct")


def execute(filters=None):
    filters = filters or {}
    now = getdate(today())
    month = _BULAN_ID.index(filters.get("bulan")) + 1 if filters.get("bulan") in _BULAN_ID else now.month
    year = int(filters.get("tahun") or now.year)
    tampilan = filters.get("tampilan") or "Ringkasan"
    if tampilan not in _TAMPILAN:
        frappe.throw(_("Tampilan tidak dikenal: {0}").format(tampilan))
    cutoff = now.day if (year, month) == (now.year, now.month) else None
    start, end = _period(year, month, cutoff)

    si_outlets = [o for o in _OUTLET_COST_CENTER if o not in _MANUAL]
    snap = load_margin(start, end)
    if snap is None:
        gl, hpp = _gl_deductions_by_outlet(start, end, si_outlets), _hpp_by_outlet(start, end, si_outlets)
    else:
        gl, hpp = snap
    sales_snap = load_sales(start, end) if tampilan == "Rincian" else {}
    terlapor = sales_snap if sales_snap is not None else _sales_by_outlet(start, end)
    is_live = snap is None or sales_snap is None
    manual = _kmt_mbg_sales_hpp(start, end)
    targets = _target_by_outlet(_BULAN_ID[month - 1])
    no_hpp = sorted(c for c in _MANUAL if not manual.get(c, {}).get("hpp_filled"))

    def detail(codes, margin_target):
        si = [c for c in codes if c not in _MANUAL]
        m = _margin_row("x", "x", {acc: sum(gl.get(o, {}).get(acc, 0) or 0 for o in si) for acc in _GL_MARGIN_ACCOUNTS},
                        sum(hpp.get(o, 0) or 0 for o in si))
        d = {"penjualan": m["sales_bruto"], "member": m["member"], "potongan": m["potongan_penjualan"], "promo": m["promo"],
             "rafaksi": m["rafaksi_discount"], "sales_bruto_2": m["sales_bruto_2"], "retur": m["retur_penjualan"],
             "sales_retur": m["sales_retur"], "sales_achv": m["sales_achv"], "hpp": m["hpp"],
             "sales_terlapor": sum(terlapor.get(o, {}).get("sales", 0) or 0 for o in si),
             "target": sum(targets.get(c, 0) or 0 for c in codes)}
        # basis hitungan margin: tanpa KMT/MBG yg HPP-nya blm diinput
        base_sales, base_target, base_retur = m["sales_achv"], sum(targets.get(c, 0) or 0 for c in si), m["sales_retur"]
        for c in codes:
            if c not in _MANUAL:
                continue
            x = manual.get(c, {"sales": 0, "hpp": 0, "hpp_filled": False})
            for k in ("penjualan", "sales_bruto_2", "sales_terlapor", "sales_retur", "sales_achv"):
                d[k] += x["sales"]
            if x["hpp_filled"]:
                d["hpp"] += x["hpp"]
                base_sales += x["sales"]; base_retur += x["sales"]; base_target += targets.get(c, 0) or 0
        has_margin = bool(si) or any(c not in no_hpp for c in codes)
        if not has_margin:
            for k in ("hpp", "deal_margin_clear", "margin_pct", "deal_margin", "margin_achv_pct", "achv_margin",
                      "target_margin_rp", "margin_achv_rp"):
                d[k] = None
        else:
            hpp_used = d["hpp"]
            d["deal_margin_clear"] = base_retur - hpp_used
            d["margin_pct"] = d["deal_margin_clear"] / base_retur * 100 if base_retur else 0
            d["deal_margin"] = base_sales - hpp_used
            margin_pct = d["deal_margin"] / base_sales if base_sales else 0
            d["margin_achv_pct"] = margin_pct * 100
            d["achv_margin"] = (margin_pct / margin_target * 100) if margin_target else 0
            d["target_margin_rp"] = (margin_target or 0) * base_target
            d["margin_achv_rp"] = d["deal_margin"] - d["target_margin_rp"]
        d["achv"] = d["sales_achv"] / d["target"] * 100 if d["target"] else 0
        d["target_margin_pct"] = margin_target * 100 if margin_target else None
        d["hpp_retur"] = d["hpp"]
        d["retur_hpp"] = 0
        return d

    off, onl, fmcg, ho = _codes(_FASHION_OFFLINE), _codes(_FASHION_ONLINE), _codes(_FMCG), _codes(_HO)
    ho_t = _ho_target(year, month)

    def row(label, codes, target, no=None, bold=0):
        r = detail(codes, target)
        r.update({"no": no, "outlet": label, "bold": bold})
        return r

    data = [{"outlet": "1.FASHION & HOME.S", "bold": 1, "is_header": 1}]
    data += [row(lab, [c], _MARGIN_TARGET_PCT.get(c), no) for c, lab, no in _FASHION_OFFLINE]
    data.append(row("Total Outlet - Offline", off, _OFFLINE_TARGET, bold=1))
    data += [row(lab, [c], _MARGIN_TARGET_PCT.get(c), no) for c, lab, no in _FASHION_ONLINE]
    data.append(row("Total Outlet - Online", onl, _ONLINE_TARGET, bold=1))
    data.append(row("Total Dept.F.H", off + onl, _MARGIN_DEPT_TARGET_PCT.get("FASHION"), bold=1))
    data.append({"outlet": "2.FMCG", "bold": 1, "is_header": 1})
    data += [row(lab, [c], _MARGIN_TARGET_PCT.get(c), no) for c, lab, no in _FMCG]
    data.append(row("Total Dept.FMCG", fmcg, _MARGIN_DEPT_TARGET_PCT.get("FMCG"), bold=1))
    data.append({"outlet": "3.HO", "bold": 1, "is_header": 1})
    data += [row(lab, [c], _MARGIN_TARGET_PCT.get(c), no) for c, lab, no in _HO]
    data.append(row("Total Dept.Holding", ho, ho_t, bold=1))
    data.append(row("HO (Offline)", off + onl + fmcg + ho, ho_t, bold=1))
    data.append(row("GRAND TOTAL", off + onl + fmcg + ho, ho_t, bold=1))

    for r in data:
        for k, v in list(r.items()):
            if isinstance(v, float):
                r[k] = round(v, 2) if k in _PCT_KEYS else round(v)

    info = f"Periode: {_BULAN_ID[month - 1]} {year} tgl 1-{end.day}"
    if is_live:
        info += "  |  (live)"
    if no_hpp:
        names = {"KMT": "Kemitraan", "MBG": "MBG"}
        info += f"  |  HPP {', '.join(names[c] for c in no_hpp)} blm diinput -> margin kosong & tdk ikut margin total"
    data.insert(0, {"outlet": info, "bold": 1, "is_info": 1})
    return (ringkasan_columns() if tampilan == "Ringkasan" else rincian_columns(month)), data


def _col(fieldname, label, fieldtype="Int", width=130):
    return {"fieldname": fieldname, "label": label, "fieldtype": fieldtype, "width": width}


def _head():
    return [_col("no", _("No"), "Data", 45), _col("outlet", _("Outlet"), "Data", 220)]


def ringkasan_columns():
    return _head() + [
        _col("target", _("TARGET SALES"), width=140), _col("sales_achv", _("SALES ACHV"), width=140),
        _col("achv", _("ACHV VS TARGET"), "Percent", 110), _col("deal_margin", _("DEAL MARGIN"), width=140),
        _col("target_margin_pct", _("TARGET MARGIN %"), "Percent", 110), _col("margin_achv_pct", _("MARGIN ACHV %"), "Percent", 110),
        _col("achv_margin", _("ACHV VS TARGET (margin)"), "Percent", 120),
        _col("target_margin_rp", _("TARGET MARGIN RP"), width=140), _col("margin_achv_rp", _("MARGIN ACHV RP"), width=140),
    ]


def rincian_columns(month):
    bulan = _BULAN_ID[month - 1][:3].upper()
    return _head() + [
        _col("target", f"{bulan} Target", width=140), _col("penjualan", _("Penjualan"), width=140),
        _col("member", _("MEMBER-X")), _col("potongan", _("Potongan Penjualan")), _col("promo", _("Promo - X")),
        _col("rafaksi", _("RAFAKSI DISCOUNT - X")), _col("sales_bruto_2", _("SALES BRUTO 2"), width=140),
        _col("sales_terlapor", _("SALES TERLAPOR"), width=140), _col("hpp", _("HPP ERP"), width=140),
        _col("retur", _("RETUR PENJUALAN")), _col("retur_hpp", _("RETUR HPP")),
        _col("sales_retur", _("SALES - RETUR"), width=140), _col("sales_achv", _("SALES ACHV"), width=140),
        _col("hpp_retur", _("HPP - RETUR"), width=140), _col("deal_margin_clear", _("deal margin clear"), width=140),
        _col("margin_pct", _("%"), "Percent", 90), _col("deal_margin", _("deal margin ++"), width=140),
    ]
