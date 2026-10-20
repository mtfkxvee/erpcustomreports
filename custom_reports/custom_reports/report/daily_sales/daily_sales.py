# Copyright (c) 2026, X-SHA and contributors
# For license information, please see license.txt
#
# Laporan "Daily Sales" - tampilan ERP dari sheet "Daily sales" file admin
# "SALES REPORT HO" (sheet yg selama ini diketik manual tiap hari & jadi sumber
# sheet ALL / DEPT.). Susunan = file: baris tgl 1-akhir bulan + nama hari,
# subtotal WEEK-1 (1-7) / WEEK-2 (8-14) / WEEK-3 (15-21) / WEEK-4 (22-akhir),
# Grand total; kolom TC, Sales, AC per outlet, total departemen + kontribusi
# (sales / total sebulan departemen itu), ALL FMCG, HO, HOLDING, MBG.
# Kolom yg di file disembunyikan (Online Cikiray, Online SP Fashion, MBG per
# toko, grup HO kosong) tetap dihitung (ikut total) tapi tdk ditampilkan.
# Sumber angka (divalidasi persis thd file Sept & 1-4 Okt 2026):
#   outlet toko  = Sales Invoice per hari (snapshot harian kalau ada, kalau tdk
#                  live), sama dgn Daily Sales vs Target
#   RSI/FDM/ANM/UMTAS/MBG = Kemitraan MBG Sales History (input dari iPOS);
#   KOREKSI ikut TOTAL Kemitraan; SKM (rollup lama) tdk dipakai -> kolom SALES
#   MARKETING = 0 spt file.
# Tabel bawah file (rata2 sales per nama hari) ada di Download Report.

import calendar

import frappe
from frappe import _
from frappe.utils import getdate, today

from custom_reports.sales_api import _BULAN_ID, _sales_by_outlet
from custom_reports.sales_snapshot import load_sales

# (kolom file, key, judul, sumber, label kolom sales, tersembunyi)
FHS = [("C", "xsc", "CIKIRAY", "XSC", "sales", 0), ("F", "xscol", "ONLINE CIKIRAY", "XSC-OL", "sales", 1),
       ("I", "psr", "PASAR", "PSR", "sales", 0), ("L", "xpy", "PANYINGKIRAN", "XPY", "sales", 0),
       ("O", "xjb", "FURNITURE", "XJB", "sales", 0), ("R", "xcw", "CIAWI", "XCW", "sales", 0),
       ("U", "ocw", "ONLINE", "OCW", "sales", 0), ("X", "xsp", "SP FASHION", "XSP", "sales", 0),
       ("AA", "xspol", "ONLINE SP FASHION", "XSP-OL", "sales", 1), ("AD", "hcw", "X-SHA RUMAH KEDUA", "HCW", "sales", 0)]
FMCG = [("AL", "xsm", "SUPERMART", "XSM", "sales", 0), ("AO", "xmj", " MANGUNREJA", "XMJ", "sales", 0),
        ("AR", "xwp", "WARUNG PEUTEUY", "XWP", "Sales", 0), ("AU", "xph", "PUSPAHIANG", "XPH", "Sales", 0),
        ("AX", "xtj", "TANJUNG JAYA", "XTJ", "Sales", 0), ("BA", "xcr", "CISARUNI", "XCR", "Sales", 0),
        ("BD", "tasmu", "TASMU", "TASMU", "Sales", 0), ("BG", "mnr", "MENARA", "MNR", "Sales", 0),
        ("BJ", "uin", "UIN GROW", "UIN", "Sales", 0), ("BM", "xsmgrow", "XSM GROW", "XSMGROW", "Sales", 0)]
KMT = [("BT", "rsi", "RSI", "RSI", "sales", 0), ("BW", "fdm", "FDM", "FDM", "sales", 0), ("BZ", "anm", "ANM", "ANM", "Sales", 0),
       ("CC", "umtas", "UMTAS", "UMTAS", "Sales", 0), ("CF", "slsm", "SALES MARKETING", None, "Sales", 0)]
MBG_STORES = [("DK", "mbg_xsm", "XSM"), ("DM", "mbg_xmj", "XMJ"), ("DO", "mbg_xwp", "XWP"), ("DQ", "mbg_xph", "XPH"),
              ("DS", "mbg_xtj", "XTJ"), ("DU", "mbg_xcr", "XCR"), ("DW", "mbg_xtm", "XTM"), ("DY", "mbg_mnr", "MNR")]
TOTALS = ("fhs", "fmcg", "kmt", "xsl", "holding")  # yg py kolom kontribusi
WEEKS = ((1, 7), (8, 14), (15, 21), (22, 31))
WEEKDAY_ORDER = ("SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT")


def _month_from(filters):
    now = getdate(today())
    month = _BULAN_ID.index(filters.get("bulan")) + 1 if filters.get("bulan") in _BULAN_ID else now.month
    year = int(filters.get("tahun") or now.year)
    return year, month


def _manual(start, end):
    """{(hari, sub_kode): (tc, sales)} dari Kemitraan MBG Sales History (tanpa SKM)."""
    rows = frappe.db.sql("""
        SELECT tanggal, sub_kode, SUM(nominal) AS s, SUM(jumlah_transaksi) AS t
        FROM `tabKemitraan MBG Sales History`
        WHERE tanggal BETWEEN %s AND %s AND sub_kode != 'SKM'
        GROUP BY tanggal, sub_kode
    """, (start, end), as_dict=True)
    return {(getdate(r.tanggal).day, r.sub_kode): (r.t or 0, r.s or 0) for r in rows}


def _cell(tc, s):
    return {"tc": tc, "s": s, "ac": (s / tc) if tc else None}


def compute(year, month):
    """Angka 1 bulan: {"days": [{day, hari, vals: {key: {tc,s,ac}}} ...], "weeks", "total", "live", ...}."""
    now = getdate(today())
    n_days = calendar.monthrange(year, month)[1]
    start, end = getdate(f"{year}-{month:02d}-01"), getdate(f"{year}-{month:02d}-{n_days:02d}")
    manual = _manual(start, end)
    live, days = [], []
    for d in range(1, n_days + 1):
        date = getdate(f"{year}-{month:02d}-{d:02d}")
        hari = calendar.day_abbr[date.weekday()].upper()
        if date > now:
            days.append({"day": d, "hari": hari, "vals": None})
            continue
        snap = load_sales(date, date) if date < now else None
        if snap is None:
            live.append(d)
            snap = _sales_by_outlet(date, date)
        base = {code: (v.get("trx", 0) or 0, v.get("sales", 0) or 0) for code, v in snap.items()}
        for (day, sub), v in manual.items():
            if day == d:
                base[sub] = v
        vals = {}

        def put(key, code):
            tc, s = base.get(code, (0, 0)) if code else (0, 0)
            vals[key] = _cell(tc, s)

        for _c, key, _l, code, _sl, _h in FHS + FMCG + KMT:
            put(key, code)
        put("xsl", "XSL")
        put("mbg", "MBG")
        for _c, key, _l in MBG_STORES:
            vals[key] = _cell(0, 0)

        def total(keys, extra=(0, 0)):
            tc = sum(vals[k]["tc"] for k in keys) + extra[0]
            s = sum(vals[k]["s"] for k in keys) + extra[1]
            return _cell(tc, s)

        vals["fhs"] = total([g[1] for g in FHS])
        vals["fmcg"] = total([g[1] for g in FMCG] + ["mbg"])           # file BP/BQ ikut MBG (SPPG)
        vals["kmt"] = total([g[1] for g in KMT], base.get("KOREKSI", (0, 0)))
        vals["allfmcg"] = {"s": vals["kmt"]["s"] + vals["fmcg"]["s"]}
        vals["holding"] = total(["fhs", "fmcg", "kmt", "xsl"])
        vals["mbgt"] = total([g[1] for g in MBG_STORES] + ["mbg"])
        days.append({"day": d, "hari": hari, "vals": vals})

    keys = [k for k in days[0]["vals"]] if days and days[0]["vals"] else None
    if keys is None:
        keys = [g[1] for g in FHS + FMCG + KMT] + ["xsl", "mbg"] + [g[1] for g in MBG_STORES] + \
               ["fhs", "fmcg", "kmt", "allfmcg", "holding", "mbgt"]

    def summ(rows):
        rows = [r["vals"] for r in rows if r["vals"]]
        if not rows:
            return None
        out = {}
        for k in keys:
            if k == "allfmcg":
                out[k] = {"s": sum(r[k]["s"] for r in rows)}
            else:
                out[k] = _cell(sum(r[k]["tc"] for r in rows), sum(r[k]["s"] for r in rows))
        return out

    weeks = [summ([x for x in days if a <= x["day"] <= min(b, n_days)]) for a, b in WEEKS]
    total = summ(days)
    month_sales = {k: (total[k]["s"] if total else 0) for k in TOTALS}

    def with_k(vals):
        if not vals:
            return vals
        for k in TOTALS:
            vals[k]["k"] = (vals[k]["s"] / month_sales[k]) if month_sales[k] else None
        return vals

    for x in days:
        with_k(x["vals"])
    for w in weeks:
        with_k(w)
    with_k(total)

    # tabel bawah file: rata2 sales per nama hari (FHS, FMCG, Kemitraan)
    avg = {}
    for grp in ("fhs", "fmcg", "kmt"):
        rows = []
        for h in WEEKDAY_ORDER:
            ds = [x for x in days if x["hari"] == h]
            s = sum(x["vals"][grp]["s"] for x in ds if x["vals"])
            rows.append((h, s, len(ds), (s / len(ds)) if ds else 0))
        tot = sum(r[1] for r in rows)
        avg[grp] = {"rows": rows, "total": (tot, n_days, tot / n_days), "avg": tot / n_days}
    return {"year": year, "month": month, "n_days": n_days, "days": days, "weeks": weeks, "total": total,
            "live": live, "avg": avg}


# ---------------------------------------------------------------------------
def visible_columns():
    """[(fieldname, label, fieldtype)] kolom yg tampil di file (yg tersembunyi dilewati)."""
    cols = []

    def three(key, title, sales_label="sales", tc_label="Tc", ac=True):
        cols.append((f"{key}_tc", f"{title} {tc_label}", "Int"))
        cols.append((f"{key}_s", f"{title} {sales_label}", "Float"))
        if ac:
            cols.append((f"{key}_ac", f"{title} Ac", "Float"))

    for _c, key, title, _code, sl, hidden in FHS:
        if not hidden:
            three(key, title.strip(), sl)
    three("fhs", "TOTAL DEPT.FASHION & H.S")
    cols.append(("fhs_k", "TOTAL DEPT.FASHION & H.S kontribusi sales", "Percent"))
    for _c, key, title, _code, sl, _h in FMCG:
        three(key, title.strip(), sl)
    three("fmcg", "OUTLET DEPT.FMCG")
    cols.append(("fmcg_k", "OUTLET DEPT.FMCG kontribusi sales", "Percent"))
    for _c, key, title, _code, sl, _h in KMT:
        three(key, title, sl)
    three("kmt", "KEMITRAAN TOTAL")
    cols.append(("kmt_k", "KEMITRAAN TOTAL kontribusi sales", "Percent"))
    cols.append(("allfmcg_s", "ALL FMCG", "Float"))
    three("xsl", "MINI SOCCER")
    cols.append(("xsl_k", "MINI SOCCER kontribusi sales", "Percent"))
    three("holding", "HOLDING")
    cols.append(("holding_k", "HOLDING kontribusi sales", "Percent"))
    three("mbg", "MBG (SPPG)", "SALES", "TC", ac=False)
    three("mbgt", "MBG TOTAL")
    return cols


def _flat(vals):
    out = {}
    for key, v in (vals or {}).items():
        for f in ("tc", "s", "ac", "k"):
            if f in v:
                out[f"{key}_{f}"] = (v[f] * 100) if (f == "k" and v[f] is not None) else v[f]
    return out


def execute(filters=None):
    filters = filters or {}
    year, month = _month_from(filters)
    m = compute(year, month)
    data = []
    total = dict(_flat(m["total"]), tgl="Grand total", bold=1)
    data.append(total)
    wi = 0
    for x in m["days"]:
        data.append(dict(_flat(x["vals"]), tgl=str(x["day"]), hari=x["hari"]))
        a, b = WEEKS[wi]
        if x["day"] == min(b, m["n_days"]):
            data.append(dict(_flat(m["weeks"][wi]), tgl=f"WEEK-{wi + 1}", bold=1))
            wi += 1
    info = f"{_BULAN_ID[month - 1]} {year}"
    if m["live"]:
        info += "  |  dihitung live (blm ada snapshot): tgl " + ", ".join(str(d) for d in m["live"])
    data.insert(0, {"tgl": info, "bold": 1, "is_info": 1})
    cols = [{"fieldname": "tgl", "label": _("TGL"), "fieldtype": "Data", "width": 90},
            {"fieldname": "hari", "label": _("HARI"), "fieldtype": "Data", "width": 55}]
    for f, label, ft in visible_columns():
        c = {"fieldname": f, "label": label, "fieldtype": ft,
             "width": 75 if f.endswith("_tc") else (125 if f.endswith("_s") else 90)}
        if ft in ("Float", "Percent"):
            c["precision"] = 2 if ft == "Percent" else 0
        cols.append(c)
    return cols, data
