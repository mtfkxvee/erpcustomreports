import statistics
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import add_days, date_diff, flt, getdate

MAX_HARI = 31
EPS = 0.005

# Urutan penentuan alasan (yang pertama cocok menang):
# harga 0 > stok minus (+HPP tercemar) > HPP tercemar > diskon > harga jauh di bawah normal
# > harga normal di bawah HPP > HPP naik > rugi tipis
R_HARGA_NOL = "Harga jual 0 (barang bonus/gratis atau lupa isi harga)"
R_STOK_MINUS = "Stok minus saat dijual (HPP pakai valuation terakhir)"
R_STOK_MINUS_CEMAR = "Stok minus saat dijual (HPP pakai valuation terakhir) + HPP tercemar"
R_CEMAR = "HPP tercemar: ada penerimaan/transaksi stok dengan rate janggal"
R_DISKON = "Diskon/promo membuat harga jual di bawah HPP"
R_JAUH = "Harga jual jauh di bawah harga normal item (kemungkinan salah harga/UOM)"
R_NORMAL_BAWAH = "Harga jual normal item ini memang di bawah HPP (setting harga belum sesuai)"
R_HPP_NAIK = "HPP naik, harga jual belum disesuaikan"
R_TIPIS = "Rugi tipis (selisih kecil, pembulatan/diskon kecil)"

TINDAKAN = {
    R_HARGA_NOL: "Cek apakah memang bonus/promo; jika lupa isi harga, koreksi.",
    R_STOK_MINUS: "Cegah jual saat stok minus; catat penerimaan barang tepat waktu.",
    R_STOK_MINUS_CEMAR: "Cegah jual saat stok minus; catat penerimaan barang tepat waktu.",
    R_CEMAR: "Koreksi rate/UOM di transaksi sumber lalu repost stock ledger.",
    R_DISKON: "Tinjau aturan diskon/promo agar tidak di bawah HPP.",
    R_JAUH: "Cek Item Price dan UOM penjualan di invoice.",
    R_NORMAL_BAWAH: "Perbarui Item Price karena harga normal di bawah HPP.",
    R_HPP_NAIK: "Naikkan harga jual mengikuti HPP terbaru.",
    R_TIPIS: "Selisih kecil, pantau saja.",
}

HPP_CEMAR_FAKTOR = 2.0      # HPP > 2x HPP normal item
HARGA_JAUH_FAKTOR = 0.7     # harga jual < 70% harga normal item
HPP_NAIK_FAKTOR = 1.01      # HPP > 101% HPP normal item


def execute(filters=None):
    filters = frappe._dict(filters or {})
    if not filters.get("from_date") or not filters.get("to_date"):
        frappe.msgprint(
            "Silakan pilih <b>Dari Tanggal</b> dan <b>Sampai Tanggal</b> terlebih dahulu.",
            indicator="orange", alert=True,
        )
        return [], []

    dari, sampai = getdate(filters.from_date), getdate(filters.to_date)
    if sampai < dari:
        frappe.throw(_("Sampai Tanggal tidak boleh sebelum Dari Tanggal"))
    if date_diff(sampai, dari) + 1 > MAX_HARI:
        frappe.throw(_("Rentang tanggal maksimal {0} hari").format(MAX_HARI))

    rows = get_loss_rows(filters, dari, sampai)
    view = filters.get("view") or "Per Item"

    if view == "Rekap Alasan":
        columns, data = rekap_view(rows)
    elif view == "Detail Baris":
        columns, data = detail_view(rows)
    else:
        columns, data = item_view(rows)

    total_rugi = sum(r["margin"] for r in rows)
    summary = [
        {"label": _("Baris Margin Minus"), "value": len(rows), "datatype": "Int", "indicator": "Red"},
        {"label": _("Jumlah Item"), "value": len({r["item_code"] for r in rows}), "datatype": "Int", "indicator": "Blue"},
        {"label": _("Total Rugi (Rp)"), "value": total_rugi, "datatype": "Currency", "indicator": "Red"},
    ]
    message = (
        "Sales Invoice submitted non-retur, hanya baris margin &lt; 0. Alasan adalah klasifikasi otomatis "
        "dari data; \"HPP naik\" dan \"harga normal di bawah HPP\" tidak dibuktikan per transaksi pembelian. "
        "HPP normal dan harga normal = median item di seluruh outlet pada periode ini."
    )
    return columns, data, message, None, summary


# ---------------------------------------------------------------- data

def get_outlet_children(outlet):
    result, queue = [], [outlet]
    while queue:
        current = queue.pop(0)
        o = frappe.db.get_value("Outlet", current, ["is_group", "name"], as_dict=True)
        if not o:
            continue
        if not o.is_group:
            result.append(current)
        else:
            for c in frappe.db.get_all("Outlet", filters={"parent_outlet": current}, fields=["name"]):
                queue.append(c["name"])
    return result if result else [outlet]


def get_outlet_list(filters):
    raw = filters.get("outlet")
    if not raw:
        return []
    if isinstance(raw, str):
        try:
            raw = frappe.parse_json(raw)
        except Exception:
            raw = [raw]
    if not isinstance(raw, (list, tuple)):
        raw = [raw]
    names = []
    for o in raw:
        names.append((o.get("value") or o.get("name") or "") if isinstance(o, dict) else str(o))
    result = []
    for o in [n for n in names if n]:
        for c in get_outlet_children(o):
            if c not in result:
                result.append(c)
    return result


def get_loss_rows(filters, dari, sampai):
    outlet_list = set(get_outlet_list(filters))
    item_filter = filters.get("item_code")

    # Dibaca per hari supaya memori terkendali; median dihitung dari SEMUA outlet.
    harga_per_item = defaultdict(list)
    hpp_per_item = defaultdict(list)
    kandidat = []
    sudah = set()

    tgl = dari
    while tgl <= sampai:
        data = frappe.db.sql(
            """
            SELECT si.name AS invoice, si.posting_date, si.posting_time, si.custom_outlet AS outlet,
                   sii.name AS row_name, sii.item_code, sii.item_name, sii.item_group, sii.warehouse,
                   sii.uom, sii.qty, sii.stock_qty, sii.rate, sii.price_list_rate,
                   sii.discount_percentage, sii.discount_amount, sii.base_net_amount, sii.incoming_rate,
                   sle.qty_after_transaction AS saldo
            FROM `tabSales Invoice` si
            JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
            LEFT JOIN `tabStock Ledger Entry` sle
                   ON sle.voucher_type = 'Sales Invoice' AND sle.voucher_no = si.name
                  AND sle.voucher_detail_no = sii.name AND sle.is_cancelled = 0
            WHERE si.docstatus = 1 AND si.is_return = 0 AND si.posting_date = %s
              AND sii.stock_qty > 0
            """,
            (tgl,),
            as_dict=True,
        )
        for r in data:
            if r.row_name in sudah:   # satu baris invoice bisa punya >1 SLE
                continue
            sudah.add(r.row_name)
            sq = flt(r.stock_qty)
            net = flt(r.base_net_amount)
            hpp = flt(r.incoming_rate)
            if net > 0:
                harga_per_item[r.item_code].append(net / sq)
            if hpp > 0:
                hpp_per_item[r.item_code].append(hpp)
            margin = net - sq * hpp
            if margin >= 0:
                continue
            if outlet_list and r.outlet not in outlet_list:
                continue
            if item_filter and r.item_code != item_filter:
                continue
            kandidat.append(r)
        tgl = add_days(tgl, 1)

    harga_normal = {k: statistics.median(v) for k, v in harga_per_item.items()}
    hpp_normal = {k: statistics.median(v) for k, v in hpp_per_item.items()}

    rows = []
    for r in kandidat:
        sq, net, hpp = flt(r.stock_qty), flt(r.base_net_amount), flt(r.incoming_rate)
        hn = hpp_normal.get(r.item_code) or 0
        pn = harga_normal.get(r.item_code) or 0
        r["penjualan"] = net
        r["qty_stok"] = sq
        r["hpp"] = hpp
        r["margin"] = net - sq * hpp
        r["hpp_normal"] = hn
        r["harga_normal"] = pn
        r["alasan"] = tentukan_alasan(r, net, sq, hpp, hn, pn)
        r["sumber"] = ""
        rows.append(r)

    isi_sumber_hpp(rows)
    rows.sort(key=lambda x: x["margin"])
    return rows


def tentukan_alasan(r, net, sq, hpp, hn, pn):
    saldo = r.saldo
    cemar = hn > 0 and hpp > HPP_CEMAR_FAKTOR * hn
    if net <= 0:
        return R_HARGA_NOL
    if saldo is not None and flt(saldo) < 0:
        return R_STOK_MINUS_CEMAR if cemar else R_STOK_MINUS
    if cemar:
        return R_CEMAR
    # diskon: ada potongan, dan harga sebelum potongan masih >= HPP (jadi potongan yang bikin rugi)
    ada_diskon = (
        flt(r.discount_percentage) > 0 or flt(r.discount_amount) > 0
        or flt(r.price_list_rate) > flt(r.rate) + EPS
    )
    harga_list_stok = flt(r.price_list_rate) * flt(r.qty) / sq if sq else 0
    if ada_diskon and harga_list_stok >= hpp:
        return R_DISKON
    if pn > 0 and (net / sq) < HARGA_JAUH_FAKTOR * pn:
        return R_JAUH
    if pn > 0 and hn > 0 and pn < hn:
        return R_NORMAL_BAWAH
    if hn > 0 and hpp > HPP_NAIK_FAKTOR * hn:
        return R_HPP_NAIK
    return R_TIPIS


def isi_sumber_hpp(rows):
    """Penerimaan stok (actual_qty > 0) di gudang yang sama dengan rate > 2x HPP normal,
    terakhir sebelum tanggal jual. Hanya dicari untuk baris yang HPP-nya tercemar."""
    perlu = [r for r in rows if r["alasan"] in (R_CEMAR, R_STOK_MINUS_CEMAR)]
    if not perlu:
        return
    items = list({r.item_code for r in perlu})
    gudang = list({r.warehouse for r in perlu})
    batas = max(str(r.posting_date) for r in perlu)
    sle = frappe.db.sql(
        """
        SELECT item_code, warehouse, voucher_type, voucher_no, incoming_rate, posting_date, posting_time
        FROM `tabStock Ledger Entry`
        WHERE is_cancelled = 0 AND actual_qty > 0
          AND item_code IN %(items)s AND warehouse IN %(gudang)s
          AND posting_date <= %(batas)s
        ORDER BY posting_date, posting_time, creation
        """,
        {"items": items, "gudang": gudang, "batas": batas},
        as_dict=True,
    )
    per_kunci = defaultdict(list)
    for s in sle:
        per_kunci[(s.item_code, s.warehouse)].append(s)

    for r in perlu:
        ambang = HPP_CEMAR_FAKTOR * r["hpp_normal"]
        pilih = None
        for s in per_kunci.get((r.item_code, r.warehouse), []):
            if (s.posting_date, s.posting_time) > (r.posting_date, r.posting_time):
                break
            if flt(s.incoming_rate) > ambang:
                pilih = s
        if pilih:
            r["sumber"] = "{0} {1}".format(pilih.voucher_type, pilih.voucher_no)


# ---------------------------------------------------------------- views

def rupiah(n):
    return ("-" if n < 0 else "") + "{:,}".format(int(round(abs(n)))).replace(",", ".")


def rekap_view(rows):
    per = defaultdict(lambda: {"baris": 0, "items": set(), "rugi": 0.0})
    for r in rows:
        p = per[r["alasan"]]
        p["baris"] += 1
        p["items"].add(r["item_code"])
        p["rugi"] += r["margin"]
    columns = [
        {"fieldname": "alasan", "label": _("Alasan"), "fieldtype": "Data", "width": 520},
        {"fieldname": "baris", "label": _("Jml Baris"), "fieldtype": "Int", "width": 100},
        {"fieldname": "items", "label": _("Jml Item"), "fieldtype": "Int", "width": 100},
        {"fieldname": "rugi", "label": _("Total Rugi (Rp)"), "fieldtype": "Currency", "width": 150},
        {"fieldname": "tindakan", "label": _("Tindakan yang disarankan"), "fieldtype": "Data", "width": 420},
    ]
    data = [
        {"alasan": k, "baris": v["baris"], "items": len(v["items"]), "rugi": v["rugi"], "tindakan": TINDAKAN.get(k, "")}
        for k, v in per.items()
    ]
    data.sort(key=lambda x: x["rugi"])
    return columns, data


def item_view(rows):
    per = defaultdict(list)
    for r in rows:
        per[r["item_code"]].append(r)

    columns = [
        {"fieldname": "item_code", "label": _("Kode Item"), "fieldtype": "Link", "options": "Item", "width": 140},
        {"fieldname": "item_name", "label": _("Nama Item"), "fieldtype": "Data", "width": 260},
        {"fieldname": "item_group", "label": _("Item Group"), "fieldtype": "Data", "width": 170},
        {"fieldname": "outlet", "label": _("Outlet"), "fieldtype": "Data", "width": 200},
        {"fieldname": "baris", "label": _("Jml Baris Rugi"), "fieldtype": "Int", "width": 110},
        {"fieldname": "penjualan", "label": _("Penjualan"), "fieldtype": "Currency", "width": 140},
        {"fieldname": "rugi", "label": _("Total Rugi (Rp)"), "fieldtype": "Currency", "width": 140},
        {"fieldname": "alasan_utama", "label": _("Alasan Utama"), "fieldtype": "Data", "width": 420},
        {"fieldname": "rincian", "label": _("Rincian Alasan"), "fieldtype": "Data", "width": 600},
        {"fieldname": "sumber", "label": _("Transaksi Sumber (HPP janggal)"), "fieldtype": "Data", "width": 300},
        {"fieldname": "contoh", "label": _("Contoh Invoice"), "fieldtype": "Data", "width": 400},
    ]
    data = []
    for kode, lst in per.items():
        per_alasan = defaultdict(lambda: [0, 0.0])
        for r in lst:
            per_alasan[r["alasan"]][0] += 1
            per_alasan[r["alasan"]][1] += r["margin"]
        urut = sorted(per_alasan.items(), key=lambda kv: kv[1][1])
        sumber = sorted({r["sumber"] for r in lst if r["sumber"]})
        contoh = []
        for r in sorted(lst, key=lambda x: x["margin"]):
            if r.invoice not in contoh:
                contoh.append(r.invoice)
            if len(contoh) >= 5:
                break
        data.append({
            "item_code": kode,
            "item_name": lst[0].item_name,
            "item_group": lst[0].item_group,
            "outlet": ", ".join(sorted({r.outlet for r in lst if r.outlet})),
            "baris": len(lst),
            "penjualan": sum(r["penjualan"] for r in lst),
            "rugi": sum(r["margin"] for r in lst),
            "alasan_utama": urut[0][0],
            "rincian": "; ".join("{0}: {1} baris, {2}".format(k, v[0], rupiah(v[1])) for k, v in urut),
            "sumber": ", ".join(sumber),
            "contoh": ", ".join(contoh),
        })
    data.sort(key=lambda x: x["rugi"])
    return columns, data


def detail_view(rows):
    columns = [
        {"fieldname": "posting_date", "label": _("Tanggal"), "fieldtype": "Date", "width": 100},
        {"fieldname": "outlet", "label": _("Outlet"), "fieldtype": "Data", "width": 90},
        {"fieldname": "invoice", "label": _("Invoice"), "fieldtype": "Link", "options": "Sales Invoice", "width": 170},
        {"fieldname": "item_code", "label": _("Kode Item"), "fieldtype": "Link", "options": "Item", "width": 140},
        {"fieldname": "item_name", "label": _("Nama Item"), "fieldtype": "Data", "width": 260},
        {"fieldname": "warehouse", "label": _("Gudang"), "fieldtype": "Data", "width": 190},
        {"fieldname": "uom", "label": _("UOM"), "fieldtype": "Data", "width": 70},
        {"fieldname": "qty", "label": _("Qty"), "fieldtype": "Float", "width": 80},
        {"fieldname": "qty_stok", "label": _("Qty Stok"), "fieldtype": "Float", "width": 90},
        {"fieldname": "rate", "label": _("Harga Satuan"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "diskon_pct", "label": _("Diskon %"), "fieldtype": "Percent", "width": 80},
        {"fieldname": "penjualan", "label": _("Penjualan"), "fieldtype": "Currency", "width": 130},
        {"fieldname": "hpp", "label": _("HPP/Satuan Stok"), "fieldtype": "Currency", "width": 130},
        {"fieldname": "margin", "label": _("Margin (Rp)"), "fieldtype": "Currency", "width": 130},
        {"fieldname": "hpp_normal", "label": _("HPP Normal (median)"), "fieldtype": "Currency", "width": 140},
        {"fieldname": "harga_normal", "label": _("Harga Normal (median)"), "fieldtype": "Currency", "width": 150},
        {"fieldname": "saldo", "label": _("Saldo Stok Setelah Jual"), "fieldtype": "Float", "width": 150},
        {"fieldname": "alasan", "label": _("Alasan"), "fieldtype": "Data", "width": 420},
        {"fieldname": "sumber", "label": _("Transaksi Sumber HPP"), "fieldtype": "Data", "width": 260},
    ]
    data = []
    for r in rows:
        data.append({
            "posting_date": r.posting_date, "outlet": r.outlet, "invoice": r.invoice,
            "item_code": r.item_code, "item_name": r.item_name, "warehouse": r.warehouse,
            "uom": r.uom, "qty": r.qty, "qty_stok": r["qty_stok"], "rate": r.rate,
            "diskon_pct": r.discount_percentage, "penjualan": r["penjualan"], "hpp": r["hpp"],
            "margin": r["margin"], "hpp_normal": r["hpp_normal"], "harga_normal": r["harga_normal"],
            "saldo": r.saldo, "alasan": r["alasan"], "sumber": r["sumber"],
        })
    return columns, data
