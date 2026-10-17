# Copyright (c) 2026, X-SHA and contributors
# For license information, please see license.txt
#
# Laporan "Monthly Service Level per Category" - tampilan dari file admin
# "SERVEL AGUSTUS FMCG" (sheet ITEM, pivot SERVEL KATEGORI & pivot supplier).
# Cara hitung SAMA dgn file (per item):
#   TOTAL PO (QTY)  = SUM(stock_qty) Purchase Order submit bulan itu
#                     (transaction_date) di warehouse group departemen
#   TOTAL RCV (QTY) = SUM(stock_qty) Purchase Receipt submit non-retur bulan
#                     itu (posting_date) utk item tsb di warehouse mana pun -
#                     tdk harus terhubung ke PO-nya (file: RCV boleh > PO)
#   NILAI PO / RCV  = qty x Item.last_purchase_rate
#   SERVEL          = nilai RCV / nilai PO
# Item yg dihitung = item yg di-PO bulan itu (penerimaan tanpa PO spt
# konsinyasi / topup tdk masuk, spt file). Kategori = Item.category (kalau
# "-" / kosong pakai item_group). Supplier per item = supplier PO dgn qty
# terbanyak, jadi total per kategori = per supplier = per item = Grand Total.
# Bulan berjalan dihitung s/d hari ini.

import frappe
from frappe import _
from frappe.utils import getdate, today

from custom_reports.custom_reports.report.monthly_sales_achievement_vs_target_net_retur_dan_potongan.monthly_sales_achievement_vs_target_net_retur_dan_potongan import _period
from custom_reports.sales_api import _BULAN_ID, _KATEGORI_DEPT_WAREHOUSE

_DEPARTEMEN = {"FMCG": "FMCG", "F&H.S": "FASHION"}


def execute(filters=None):
    filters = filters or {}
    now = getdate(today())
    month = _BULAN_ID.index(filters.get("bulan")) + 1 if filters.get("bulan") in _BULAN_ID else now.month
    year = int(filters.get("tahun") or now.year)
    dept_label = filters.get("departemen") or "FMCG"
    tampilan = filters.get("tampilan") or "Kategori"
    wh = _KATEGORI_DEPT_WAREHOUSE.get(_DEPARTEMEN.get(dept_label, "FMCG"))
    start, end = _period(year, month, now.day if (year, month) == (now.year, now.month) else None)

    items = _service_level_items(start, end, wh)
    tot_po, tot_rcv = sum(x["nilai_po"] for x in items), sum(x["nilai_rcv"] for x in items)
    grand = {"label": "Grand Total", "bold": 1, "po_qty": sum(x["po_qty"] for x in items),
             "rcv_qty": sum(x["rcv_qty"] for x in items), "nilai_po": tot_po, "nilai_rcv": tot_rcv,
             "servel": _servel(tot_rcv, tot_po)}

    if tampilan == "Item":
        data = [dict(x, label=x["item_code"], servel=_servel(x["nilai_rcv"], x["nilai_po"]))
                for x in sorted(items, key=lambda x: (-x["nilai_rcv"], -x["nilai_po"], x["item_code"]))]
    else:
        key = "kategori" if tampilan == "Kategori" else "supplier_name"
        groups = {}
        for x in items:
            g = groups.setdefault(x[key] or "-", {"label": x[key] or "-", "po_qty": 0, "rcv_qty": 0, "nilai_po": 0, "nilai_rcv": 0})
            for k in ("po_qty", "rcv_qty", "nilai_po", "nilai_rcv"):
                g[k] += x[k]
        data = sorted(groups.values(), key=lambda g: (-g["nilai_po"], -g["nilai_rcv"], g["label"]))
        for g in data:
            g["servel"] = _servel(g["nilai_rcv"], g["nilai_po"])

    info = (f"{dept_label}  |  {_BULAN_ID[month - 1]} {year} tgl 1-{end.day}  |  per {tampilan.lower()}"
            f"  |  {len(items)} item di-PO")
    return get_columns(tampilan), [{"label": info, "bold": 1, "is_info": 1}, grand] + data


def _servel(rcv, po):
    return round(rcv / po * 100, 4) if po else 0


def _service_level_items(start, end, warehouse_group):
    """[{item_code, item_name, kategori, supplier_name, po_qty, rcv_qty,
    last_purchase_rate, nilai_po, nilai_rcv}] - item yg di-PO di periode itu."""
    bounds = frappe.db.get_value("Warehouse", warehouse_group, ["lft", "rgt"], as_dict=True)
    if not bounds:
        return []
    params = {"start": start, "end": end, "lft": bounds.lft, "rgt": bounds.rgt}
    po_rows = frappe.db.sql("""
        SELECT poi.item_code, po.supplier, SUM(poi.stock_qty) AS qty
        FROM `tabPurchase Order Item` poi
        JOIN `tabPurchase Order` po ON po.name = poi.parent
        JOIN `tabWarehouse` w ON w.name = poi.warehouse
        WHERE po.docstatus = 1 AND po.transaction_date BETWEEN %(start)s AND %(end)s
          AND w.lft >= %(lft)s AND w.rgt <= %(rgt)s
        GROUP BY poi.item_code, po.supplier
    """, params, as_dict=True)
    if not po_rows:
        return []
    po_qty, supplier = {}, {}
    for r in po_rows:
        po_qty[r.item_code] = po_qty.get(r.item_code, 0) + (r.qty or 0)
        best = supplier.get(r.item_code)
        if best is None or (r.qty or 0) > best[1] or ((r.qty or 0) == best[1] and r.supplier < best[0]):
            supplier[r.item_code] = (r.supplier, r.qty or 0)
    codes = list(po_qty)

    # RCV item2 itu di warehouse mana pun (file: barang FMCG yg diterima di
    # GUDANG FHS tetap dihitung). PR cancel tdk dihitung (file Agustus masih
    # ikut menghitung PR cancel).
    rcv_rows = frappe.db.sql("""
        SELECT pri.item_code, SUM(pri.stock_qty) AS qty
        FROM `tabPurchase Receipt Item` pri
        JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
        WHERE pr.docstatus = 1 AND pr.is_return = 0 AND pr.posting_date BETWEEN %(start)s AND %(end)s
          AND pri.item_code IN %(codes)s
        GROUP BY pri.item_code
    """, dict(params, codes=codes), as_dict=True)
    rcv = {r.item_code: r.qty or 0 for r in rcv_rows}

    info = {r.name: r for r in frappe.db.sql("""
        SELECT name, item_name, category, item_group, last_purchase_rate
        FROM `tabItem` WHERE name IN %(codes)s
    """, {"codes": codes}, as_dict=True)}
    sup_ids = list({s for s, _q in supplier.values() if s})
    sup_name = {r.name: r.supplier_name for r in frappe.db.sql("""
        SELECT name, supplier_name FROM `tabSupplier` WHERE name IN %(ids)s
    """, {"ids": sup_ids}, as_dict=True)} if sup_ids else {}

    out = []
    for code in codes:
        it = info.get(code) or frappe._dict()
        cat = (it.category or "").strip()
        if not cat or cat == "-":
            cat = it.item_group or "-"
        rate = it.last_purchase_rate or 0
        s = supplier[code][0]
        out.append({"item_code": code, "item_name": it.item_name or code, "kategori": cat,
                    "supplier_name": sup_name.get(s) or s or "-", "po_qty": po_qty[code],
                    "rcv_qty": rcv.get(code, 0), "last_purchase_rate": rate,
                    "nilai_po": po_qty[code] * rate, "nilai_rcv": rcv.get(code, 0) * rate})
    return out


def get_columns(tampilan):
    def col(fieldname, label, fieldtype="Float", width=150, precision=0):
        c = {"fieldname": fieldname, "label": label, "fieldtype": fieldtype, "width": width}
        if precision is not None:
            c["precision"] = precision
        return c
    nilai = [col("nilai_po", _("TOTAL NILAI PO (RP)")), col("nilai_rcv", _("TOTAL NILAI RCV (RP)")),
             col("servel", _("SERVEL"), "Percent", 100, 2)]
    if tampilan == "Item":
        return [col("label", _("ID"), "Data", 140, None), col("item_name", _("ITEM NAME"), "Data", 260, None),
                col("kategori", _("KATEGORI"), "Data", 150, None),
                col("po_qty", _("TOTAL PO (QTY)"), width=110), col("rcv_qty", _("TOTAL RCV (QTY)"), width=110),
                col("last_purchase_rate", _("LAST PURCHASE RATE"), width=120),
                nilai[0], nilai[1], col("supplier_name", _("SUPPLIER"), "Data", 240, None), nilai[2]]
    first = _("KATEGORI") if tampilan == "Kategori" else _("SUPPLIER")
    return [col("label", first, "Data", 280, None), col("po_qty", _("TOTAL PO (QTY)"), width=110),
            col("rcv_qty", _("TOTAL RCV (QTY)"), width=110)] + nilai
