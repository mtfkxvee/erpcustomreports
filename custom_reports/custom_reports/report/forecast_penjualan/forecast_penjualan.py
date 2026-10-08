import frappe


# Report ini sebelumnya tersimpan di DB (is_standard = No, jalan di sandbox
# safe_exec). Dipindah jadi file supaya ter-versi di git. Badan main() SENGAJA
# dibiarkan apa adanya dari versi sandbox -- termasuk gayanya (semua helper jadi
# closure, frappe dilewatkan sebagai argumen, tanpa import di dalam) -- supaya
# perilakunya terbukti identik. Jangan dirapikan tanpa membandingkan output lagi.
# Sumber lama: workflows/forecast/forecast_penjualan_report.py


def main(frappe, filters):
    # ------------------------------------------------------------------
    # Forecast Penjualan (Script Report, dijalankan di sandbox Frappe)
    # Aktual  = SUM(grand_total - loyalty_amount) Sales Invoice non-retur (sama dengan
    #           Laporan Penjualan Harian). Sebelum SI_FROM dipakai histori impor
    #           (Outlet Daily Sales History).
    # Forecast = 50% baseline (median 4 hari-yang-sama terakhir, hari normal)
    #          + 50% tahun lalu sejajar (364 hari lalu) x faktor pertumbuhan YoY 8 minggu.
    #          Hari libur/event: pembanding = hari libur/event yang sama tahun lalu
    #          (dicocokkan lewat doctype Indonesia Day Calendar).
    # Catatan sandbox: tanpa import, tanpa nama berawalan underscore, semua helper
    # berupa closure di dalam main().
    # ------------------------------------------------------------------
    SCOPE = ["MNR", "OCW", "PSR", "TASMU", "XCR", "XCW", "XJB", "XMJ", "XPH", "XPY", "XSC", "XSM", "XSP", "XTJ", "XWP"]
    VOLATILE = ["XJB", "OCW", "XPY", "XSP"]
    SI_FROM = "2026-06-01"
    K_BASE = 4
    GROWTH_DAYS = 56
    DAYS_ID = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]

    U = frappe.utils
    today = U.getdate(U.nowdate())
    lastdone = U.add_days(today, -1)
    si_from = U.getdate(SI_FROM)
    from_date = U.getdate(filters.get("from_date") or today)
    to_date = U.getdate(filters.get("to_date") or U.get_last_day(today))
    if to_date < from_date:
        frappe.throw("Sampai Tanggal tidak boleh lebih awal dari Dari Tanggal")
    if U.date_diff(to_date, from_date) > 93:
        frappe.throw("Rentang tanggal maksimal 93 hari")
    view = filters.get("view") or "Harian"

    # ---- outlet yang dipilih (kosong = semua outlet scope) ----
    raw = str(filters.get("outlet") or "")
    for ch in '[]{}"\',:':
        raw = raw.replace(ch, " ")
    picked = raw.split()
    parent_rows = frappe.db.sql("select name, parent_outlet from `tabOutlet`", as_dict=True)
    parent_of = {}
    for pr in parent_rows:
        parent_of[pr["name"]] = pr["parent_outlet"]
    outlets = [o for o in SCOPE if o in picked or parent_of.get(o) in picked]
    warn = ""
    if picked and not outlets:
        warn = "Outlet yang dipilih di luar scope forecast, ditampilkan semua outlet scope."
    if not outlets:
        outlets = list(SCOPE)

    # ---- data ----
    lo = U.add_days(from_date, -(364 + 120))
    vals = {}
    for r in frappe.db.sql(
        "select outlet as o, tanggal as d, nominal as v from `tabOutlet Daily Sales History` "
        "where outlet in %(o)s and tanggal >= %(lo)s and tanggal < %(si)s",
        {"o": tuple(outlets), "lo": lo, "si": si_from}, as_dict=True):
        vals[r["o"] + "|" + str(r["d"])] = r["v"] or 0
    for r in frappe.db.sql(
        "select si.custom_outlet as o, si.posting_date as d, "
        "sum(si.grand_total - coalesce(si.loyalty_amount, 0)) as v "
        "from `tabSales Invoice` si "
        "where si.docstatus = 1 and si.is_return = 0 and si.custom_outlet in %(o)s "
        "and si.posting_date >= %(si)s and si.posting_date <= %(last)s "
        "group by si.custom_outlet, si.posting_date",
        {"o": tuple(outlets), "si": si_from, "last": lastdone}, as_dict=True):
        vals[r["o"] + "|" + str(r["d"])] = r["v"] or 0

    # Target harian dari "Sales Target Outlet" -> child "Sales Target Daily".
    # UPPER(COALESCE(so.outlet, std.parent)): nama dokumen Sales Target Outlet TIDAK
    # selalu sama dengan kode outlet -- ada yang hash ("ib614lonrt" utk XSL,
    # "i9nrri1c58" utk XSC-OL), ada yang beda case ("xsc" utk XSC), dan XJB field
    # `outlet`-nya KOSONG sehingga harus fallback ke nama dokumen. Pola ini sama
    # dengan _target_by_outlet() di sales_api.py. Memfilter std.parent langsung
    # (spt get_target_map di laporan_penjualan_harian) akan melewatkan outlet2 itu.
    tgt = {}
    for r in frappe.db.sql(
        "select upper(coalesce(so.outlet, std.parent)) as o, std.tanggal as d, "
        "sum(std.target_harian) as v "
        "from `tabSales Target Daily` std "
        "join `tabSales Target Outlet` so on so.name = std.parent "
        "where std.tanggal >= %(a)s and std.tanggal <= %(b)s "
        "and upper(coalesce(so.outlet, std.parent)) in %(o)s "
        "group by upper(coalesce(so.outlet, std.parent)), std.tanggal",
        {"a": from_date, "b": to_date, "o": tuple(outlets)}, as_dict=True):
        tgt[r["o"] + "|" + str(r["d"])] = r["v"] or 0

    cal = {}
    byname = {}
    for r in frappe.db.sql(
        "select name as d, day_type, holiday_name, event_tag from `tabIndonesia Day Calendar` order by name",
        as_dict=True):
        cal[str(r["d"])] = r
        if r["holiday_name"]:
            k = r["holiday_name"] + "|" + str(r["d"])[:4]
            if k not in byname:
                byname[k] = []
            byname[k].append(str(r["d"]))

    # ---- helper ----
    def val(o, d):
        if d > lastdone:
            return None
        return vals.get(o + "|" + str(d))

    def isnormal(d):
        c = cal.get(str(d))
        return c is not None and c["day_type"] in ("Weekday", "Weekend") and not c["event_tag"]

    def special(d):
        c = cal.get(str(d))
        return c is not None and (c["day_type"] in ("Libur Nasional", "Cuti Bersama") or c["event_tag"] not in (None, ""))

    def median(xs):
        s = sorted(xs)
        n = len(s)
        if n == 0:
            return None
        if n % 2 == 1:
            return s[n // 2]
        return (s[n // 2 - 1] + s[n // 2]) / 2.0

    def pct(a, b):
        if a is None or not b:
            return None
        return (a / b - 1) * 100

    growth_memo = {}

    def growth(o, cutd):
        key = o + "|" + str(cutd)
        if key in growth_memo:
            return growth_memo[key]
        sa = 0
        sb = 0
        for i in range(GROWTH_DAYS):
            x = U.add_days(cutd, -i)
            if x < si_from:
                break
            y = U.add_days(x, -364)
            if isnormal(x) and isnormal(y):
                a = val(o, x)
                b = val(o, y)
                if a is not None and b:
                    sa += a
                    sb += b
        g = None
        if sb > 0:
            g = max(0.4, min(2.5, sa / sb))
        growth_memo[key] = g
        return g

    def baseline(o, d):
        x = d
        while x > lastdone:
            x = U.add_days(x, -7)
        if x == d:
            x = U.add_days(x, -7)
        got = []
        while len(got) < K_BASE and x >= si_from:
            v = val(o, x)
            if v is not None and isnormal(x):
                got.append(v)
            x = U.add_days(x, -7)
        return median(got)

    def ly_ref(d):
        c = cal.get(str(d))
        if c is None:
            return None
        y = d.year
        if c["holiday_name"]:
            cur = byname.get(c["holiday_name"] + "|" + str(y))
            prev = byname.get(c["holiday_name"] + "|" + str(y - 1))
            if cur and prev and str(d) in cur:
                i = cur.index(str(d))
                if i < len(prev):
                    return U.getdate(prev[i])
        tag = c["event_tag"]
        if tag in ("Ramadan", "Lebaran"):
            a = byname.get("Hari Idul Fitri|" + str(y))
            b = byname.get("Hari Idul Fitri|" + str(y - 1))
            if a and b:
                return U.add_days(U.getdate(b[0]), U.date_diff(d, U.getdate(a[0])))
        if (tag in ("Nataru", "Harbolnas") or c["holiday_name"]) and not (d.month == 2 and d.day == 29):
            return U.getdate("%d-%02d-%02d" % (y - 1, d.month, d.day))
        return None

    def forecast(o, d):
        cutd = U.add_days(d, -1)
        if cutd > lastdone:
            cutd = lastdone
        b = baseline(o, d)
        g = growth(o, cutd)
        yoy = None
        if special(d):
            ref = ly_ref(d)
            cf = None
            if ref is not None:
                lv = val(o, ref)
                if lv is not None:
                    if g:
                        yoy = lv * g
                    around = []
                    for j in (-28, -21, -14, -7, 7, 14, 21, 28):
                        x = U.add_days(ref, j)
                        v = val(o, x)
                        if v is not None and isnormal(x):
                            around.append(v)
                    den = median(around)
                    if den:
                        cf = max(0.3, min(3.0, lv / den))
            comp_b = b * (cf if cf else 1.0) if b is not None else None
        else:
            comp_b = b
            ly = U.add_days(d, -364)
            lv = val(o, ly) if isnormal(ly) else None
            if lv is not None and g:
                yoy = lv * g
        if comp_b is not None and yoy is not None:
            return 0.5 * comp_b + 0.5 * yoy
        if comp_b is not None:
            return comp_b
        return yoy

    def lm_date(d):
        pm = U.get_first_day(U.add_months(d, -1))
        first = U.add_days(pm, (d.weekday() - pm.weekday()) % 7)
        cand = U.add_days(first, 7 * ((d.day - 1) // 7))
        if cand.month != pm.month:
            cand = U.add_days(cand, -7)
        return cand

    def total_on(d):
        s = 0
        n = 0
        for o in outlets:
            v = val(o, d)
            if v is not None:
                s += v
                n += 1
        return s, n

    def complete_on(d):
        t = total_on(d)
        if t[1] == len(outlets):
            return t[0]
        return None

    def target_on(d):
        # Sengaja ikut konvensi complete_on(): kosong kalau TIDAK semua outlet
        # terpilih punya baris target di tanggal itu. Lebih baik kosong daripada
        # menampilkan jumlah separuh yang terlihat seperti target penuh.
        s = 0
        n = 0
        for o in outlets:
            v = tgt.get(o + "|" + str(d))
            if v is not None:
                s += v
                n += 1
        if n == len(outlets):
            return s
        return None

    # ---- baris harian ----
    rows = []
    d = from_date
    while d <= to_date:
        c = cal.get(str(d))
        act = None
        if d <= lastdone:
            t = total_on(d)
            if t[1] > 0:
                act = t[0]
        fs = 0
        nf = 0
        for o in outlets:
            f = forecast(o, d)
            if f is not None:
                fs += f
                nf += 1
        fc = fs if nf > 0 else None
        nilai = act if act is not None else fc
        lmd = lm_date(d)
        lyd = U.add_days(d, -364)
        lm = complete_on(lmd)
        ly = complete_on(lyd)
        tag = ""
        if c is not None:
            tag = c["holiday_name"] or c["event_tag"] or ""
        rows.append({
            "posting_date": d, "hari": DAYS_ID[d.weekday()], "wd": d.weekday(),
            "day_type": c["day_type"] if c is not None else "",
            "event": tag, "actual": act, "forecast": fc, "target": target_on(d),
            "var_pct": pct(act, fc) if act is not None else None,
            "nilai": nilai, "lm_date": lmd, "lm": lm, "lm_pct": pct(nilai, lm),
            "ly_date": lyd, "ly": ly, "ly_pct": pct(nilai, ly),
        })
        d = U.add_days(d, 1)

    # ---- ringkasan ----
    tot_act = sum([r["actual"] for r in rows if r["actual"] is not None])
    tot_fc_rest = sum([r["forecast"] for r in rows if r["actual"] is None and r["forecast"] is not None])
    tot_nilai = sum([r["nilai"] for r in rows if r["nilai"] is not None])
    lm_ok = len([r for r in rows if r["lm"] is not None]) == len(rows)
    ly_ok = len([r for r in rows if r["ly"] is not None]) == len(rows)
    tgt_ok = len([r for r in rows if r["target"] is not None]) == len(rows)
    tot_tgt = sum([r["target"] for r in rows]) if tgt_ok else None
    tot_lm = sum([r["lm"] for r in rows]) if lm_ok else None
    tot_ly = sum([r["ly"] for r in rows]) if ly_ok else None
    apes = [abs(r["actual"] / r["forecast"] - 1) * 100 for r in rows if r["actual"] and r["forecast"]]
    mape = sum(apes) / len(apes) if apes else None

    summary = [
        {"label": "Aktual s/d Kemarin", "value": tot_act, "datatype": "Currency", "indicator": "green"},
        {"label": "Forecast Sisa Hari", "value": tot_fc_rest, "datatype": "Currency", "indicator": "orange"},
        {"label": "Proyeksi Periode", "value": tot_nilai, "datatype": "Currency", "indicator": "blue"},
        {"label": "vs Bulan Lalu (%)", "value": pct(tot_nilai, tot_lm) if tot_lm else 0, "datatype": "Percent", "indicator": "purple"},
        {"label": "vs Tahun Lalu (%)", "value": pct(tot_nilai, tot_ly) if tot_ly else 0, "datatype": "Percent", "indicator": "purple"},
        {"label": "Galat Forecast Hari Lampau (MAPE)", "value": mape if mape is not None else 0, "datatype": "Percent", "indicator": "red"},
    ]

    cur = "Currency"
    pc = "Percent"
    chart = None
    if view == "Harian":
        columns = [
            {"fieldname": "posting_date", "label": "Tanggal", "fieldtype": "Date", "width": 100},
            {"fieldname": "hari", "label": "Hari", "fieldtype": "Data", "width": 75},
            {"fieldname": "day_type", "label": "Tipe Hari", "fieldtype": "Data", "width": 110},
            {"fieldname": "event", "label": "Libur / Event", "fieldtype": "Data", "width": 170},
            {"fieldname": "actual", "label": "Aktual (Rp)", "fieldtype": cur, "width": 140},
            {"fieldname": "forecast", "label": "Forecast (Rp)", "fieldtype": cur, "width": 140},
            {"fieldname": "target", "label": "Target (Rp)", "fieldtype": cur, "width": 140},
            {"fieldname": "var_pct", "label": "Aktual vs Forecast (%)", "fieldtype": pc, "width": 120},
            {"fieldname": "lm_date", "label": "Tgl Bulan Lalu", "fieldtype": "Date", "width": 100},
            {"fieldname": "lm", "label": "Bulan Lalu (Rp)", "fieldtype": cur, "width": 140},
            {"fieldname": "lm_pct", "label": "vs Bulan Lalu (%)", "fieldtype": pc, "width": 110},
            {"fieldname": "ly_date", "label": "Tgl Tahun Lalu", "fieldtype": "Date", "width": 100},
            {"fieldname": "ly", "label": "Tahun Lalu (Rp)", "fieldtype": cur, "width": 140},
            {"fieldname": "ly_pct", "label": "vs Tahun Lalu (%)", "fieldtype": pc, "width": 110},
        ]
        out = list(rows)
        out.append({
            "posting_date": None, "hari": "TOTAL", "day_type": "", "event": "",
            "actual": tot_act, "forecast": sum([r["forecast"] for r in rows if r["forecast"] is not None]),
            "target": tot_tgt,
            "var_pct": None, "lm": tot_lm, "lm_pct": pct(tot_nilai, tot_lm) if tot_lm else None,
            "ly": tot_ly, "ly_pct": pct(tot_nilai, tot_ly) if tot_ly else None,
        })
        if len(rows) > 1:
            datasets = [
                {"name": "Aktual", "values": [r["actual"] or 0 for r in rows], "chartType": "bar"},
                {"name": "Forecast", "values": [r["forecast"] or 0 for r in rows], "chartType": "line"},
            ]
            if lm_ok:
                datasets.append({"name": "Bulan Lalu", "values": [r["lm"] for r in rows], "chartType": "line"})
            if ly_ok:
                datasets.append({"name": "Tahun Lalu", "values": [r["ly"] for r in rows], "chartType": "line"})
            chart = {
                "data": {"labels": [str(r["posting_date"]) for r in rows], "datasets": datasets},
                "type": "axis-mixed", "fieldtype": "Currency", "height": 300,
                "axisOptions": {"xIsSeries": 1},
            }
    else:
        if view == "Tipe Hari":
            order = ["Weekday", "Weekend", "Libur Nasional", "Cuti Bersama"]
            first = {"fieldname": "grp", "label": "Tipe Hari", "fieldtype": "Data", "width": 140}
            keyf = "day_type"
        else:
            order = [0, 1, 2, 3, 4, 5, 6]
            first = {"fieldname": "grp", "label": "Hari", "fieldtype": "Data", "width": 140}
            keyf = "wd"
        columns = [
            first,
            {"fieldname": "n", "label": "Jumlah Hari", "fieldtype": "Int", "width": 100},
            {"fieldname": "total", "label": "Total Aktual+Forecast (Rp)", "fieldtype": cur, "width": 190},
            {"fieldname": "avg", "label": "Rata-rata/Hari (Rp)", "fieldtype": cur, "width": 160},
            {"fieldname": "avg_lm", "label": "Rata-rata Bulan Lalu (Rp)", "fieldtype": cur, "width": 180},
            {"fieldname": "lm_pct", "label": "vs Bulan Lalu (%)", "fieldtype": pc, "width": 120},
            {"fieldname": "avg_ly", "label": "Rata-rata Tahun Lalu (Rp)", "fieldtype": cur, "width": 180},
            {"fieldname": "ly_pct", "label": "vs Tahun Lalu (%)", "fieldtype": pc, "width": 120},
        ]
        out = []
        for g in order:
            sub = [r for r in rows if r[keyf] == g and r["nilai"] is not None]
            if not sub:
                continue
            tot = sum([r["nilai"] for r in sub])
            sl = [r for r in sub if r["lm"] is not None]
            sy = [r for r in sub if r["ly"] is not None]
            a_lm = sum([r["nilai"] for r in sl]) / len(sl) if sl else None
            b_lm = sum([r["lm"] for r in sl]) / len(sl) if sl else None
            a_ly = sum([r["nilai"] for r in sy]) / len(sy) if sy else None
            b_ly = sum([r["ly"] for r in sy]) / len(sy) if sy else None
            out.append({
                "grp": g if view == "Tipe Hari" else DAYS_ID[g], "n": len(sub), "total": tot, "avg": tot / len(sub),
                "avg_lm": b_lm, "lm_pct": pct(a_lm, b_lm), "avg_ly": b_ly, "ly_pct": pct(a_ly, b_ly),
            })
        if out:
            chart = {
                "data": {"labels": [str(r["grp"]) for r in out],
                         "datasets": [{"name": "Rata-rata/Hari", "values": [r["avg"] for r in out]}]},
                "type": "bar", "fieldtype": "Currency", "height": 280,
            }

    msg = ("<b>Metode:</b> forecast = 50% median 4 hari-yang-sama terakhir + 50% tahun lalu sejajar x pertumbuhan YoY 8 minggu; "
           "hari libur/event dibandingkan dengan libur/event yang sama tahun lalu. "
           "Aktual = grand_total - loyalty_amount Sales Invoice non-retur (sama dengan Laporan Penjualan Harian); "
           "sebelum " + SI_FROM + " memakai histori impor. "
           "Pembanding bulan lalu/tahun lalu kosong bila datanya tidak lengkap di semua outlet terpilih (mis. Apr-Mei 2026). "
           "<b>Target</b> = jumlah target harian (Sales Target Outlet -> Target Per Hari) untuk outlet terpilih; "
           "kosong bila ada outlet terpilih yang belum punya target di tanggal itu. "
           "Outlet dengan penjualan bergelombang (" + ", ".join(VOLATILE) + ") akurasinya rendah per hari. "
           "Hari libur/event (mis. Nataru) hanya punya 1 tahun pembanding sehingga kurang stabil.")
    if warn:
        msg = "<b style='color:#c0392b'>" + warn + "</b><br>" + msg
    return [columns, out, msg, chart, summary, None]


def execute(filters=None):
    return main(frappe, filters)
