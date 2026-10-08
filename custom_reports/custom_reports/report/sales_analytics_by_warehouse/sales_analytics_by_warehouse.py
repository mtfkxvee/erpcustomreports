import frappe
from frappe import _, scrub
from frappe.utils import getdate, flt, add_days, add_to_date
from dateutil.relativedelta import relativedelta, MO


TREE_TYPE_CONFIG = {
    "Item Group":     {"entity_field": "i.item_group",     "extra_join": "JOIN `tabItem` i ON i.name = sii.item_code", "parent_field": "parent_item_group",    "is_group": True},
    "Item":           {"entity_field": "sii.item_code",    "extra_join": "",                                            "parent_field": None,                    "is_group": False},
    "Customer":       {"entity_field": "si.customer",      "extra_join": "",                                            "parent_field": None,                    "is_group": False},
    "Customer Group": {"entity_field": "si.customer_group","extra_join": "",                                            "parent_field": "parent_customer_group", "is_group": True},
    "Territory":      {"entity_field": "si.territory",     "extra_join": "",                                            "parent_field": "parent_territory",      "is_group": True},
    "Order Type":     {"entity_field": "si.order_type",    "extra_join": "",                                            "parent_field": None,                    "is_group": False},
    "Project":        {"entity_field": "si.project",       "extra_join": "",                                            "parent_field": None,                    "is_group": False},
}


def execute(filters=None):
    if not filters:
        filters = {}
    filters = frappe._dict(filters)
    # Konversi warehouse MultiSelectList ke list string
    if filters.get("warehouses") and isinstance(filters.get("warehouses"), list):
        wh_raw = []
        for w in filters.warehouses:
            if isinstance(w, dict):
                wh_raw.append(w.get("value") or w.get("name") or "")
            else:
                wh_raw.append(str(w))
        filters.warehouses = [w for w in wh_raw if w]
    # Konversi outlet MultiSelectList ke list string
    if filters.get("outlets") and isinstance(filters.get("outlets"), list):
        ol_raw = []
        for o in filters.outlets:
            if isinstance(o, dict):
                ol_raw.append(o.get("value") or o.get("name") or "")
            else:
                ol_raw.append(str(o))
        filters.outlets = [o for o in ol_raw if o]
    filters.from_date = getdate(filters.get("from_date") or frappe.defaults.get_user_default("year_start_date"))
    filters.to_date   = getdate(filters.get("to_date")   or frappe.defaults.get_user_default("year_end_date"))
    if not filters.get("tree_type"):  filters.tree_type = "Item Group"
    if not filters.get("range"):      filters.range = "Monthly"
    if not filters.get("company"):    filters.company = frappe.defaults.get_user_default("company") or frappe.db.get_single_value("Global Defaults", "default_company")
    periodic_daterange = get_period_date_ranges(filters)
    columns  = get_columns(filters, periodic_daterange)
    data     = get_data(filters, periodic_daterange)
    chart    = get_chart_data(columns, data, filters)
    cfg = TREE_TYPE_CONFIG.get(filters.tree_type, {})
    skip_total_row = 1 if cfg.get("is_group") else 0
    return columns, data, None, chart, None, skip_total_row


def get_period_date_ranges(filters):
    from_date = getdate(filters.from_date)
    to_date   = getdate(filters.to_date)
    inc = {"Monthly": 1, "Quarterly": 3, "Yearly": 12}.get(filters.range, 1)
    if filters.range in ("Monthly", "Quarterly"):
        from_date = from_date.replace(day=1)
    elif filters.range == "Weekly":
        from_date = from_date + relativedelta(from_date, weekday=MO(-1))
    periods = []
    for _ in range(1, 53):
        if filters.range == "Weekly":
            end = add_days(from_date, 6)
        else:
            end = add_to_date(from_date, months=inc, days=-1)
        if end > to_date: end = to_date
        periods.append(end)
        from_date = add_days(end, 1)
        if end == to_date: break
    return periods


def get_period_label(end_date, range_type):
    months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    if range_type == "Weekly":
        return "Week {} {}".format(end_date.isocalendar()[1], end_date.year)
    elif range_type == "Monthly":
        return "{} {}".format(months[end_date.month - 1], end_date.year)
    elif range_type == "Quarterly":
        return "Quarter {} {}".format(((end_date.month - 1) // 3) + 1, end_date.year)
    else:
        return str(end_date.year)


def get_warehouse_children(warehouse):
    """Ambil semua child warehouse (termasuk dirinya sendiri) via nested set lft/rgt."""
    wh = frappe.db.get_value("Warehouse", warehouse, ["lft", "rgt", "is_group"], as_dict=True)
    if not wh:
        return [warehouse]
    if not wh.is_group:
        return [warehouse]
    children = frappe.db.sql(
        "SELECT name FROM `tabWarehouse`"
        " WHERE lft >= %s AND rgt <= %s AND is_group = 0",
        (wh.lft, wh.rgt), as_dict=True
    )
    return [c["name"] for c in children] if children else [warehouse]


def get_outlet_descendants(outlet):
    """Outlet yang dipilih + SEMUA turunannya, lewat nested set lft/rgt.

    Sengaja TIDAK memakai pola get_outlet_children() di laporan_penjualan_harian
    (telusur parent_outlet yang berhenti di is_group=0 dan membuang node
    induknya sendiri). Dua kondisi di data produksi bikin pola itu membuang
    data tanpa gejala:
      - Outlet group FMCG dipakai LANGSUNG di Sales Invoice, jadi node induk
        tidak boleh dibuang dari hasil expand.
      - UIN is_group=0 TAPI punya anak BGROW, jadi telusur yang berhenti begitu
        ketemu is_group=0 tidak akan pernah sampai ke BGROW.
    lft/rgt sudah diverifikasi konsisten untuk 29 outlet yang ada.
    """
    o = frappe.db.get_value("Outlet", outlet, ["lft", "rgt"], as_dict=True)
    if not o or not o.lft:
        return [outlet]
    rows = frappe.db.sql(
        "SELECT name FROM `tabOutlet` WHERE lft >= %s AND rgt <= %s",
        (o.lft, o.rgt), as_dict=True
    )
    return [r["name"] for r in rows] if rows else [outlet]


def get_outlet_list(filters):
    """Daftar outlet final untuk WHERE: tiap pilihan di-expand ke turunannya."""
    outlet_raw = filters.get("outlets")
    if not outlet_raw:
        return []
    if isinstance(outlet_raw, list):
        raw_list = []
        for o in outlet_raw:
            if isinstance(o, dict):
                raw_list.append(o.get("value") or o.get("name") or "")
            else:
                raw_list.append(str(o))
        raw_list = [o for o in raw_list if o]
    else:
        raw_list = [str(outlet_raw)]
    result = []
    for ol in raw_list:
        for d in get_outlet_descendants(ol):
            if d not in result:
                result.append(d)
    return result


def get_columns(filters, periodic_daterange):
    cols = [{"label": _(filters.tree_type), "fieldname": "entity", "fieldtype": "Data", "width": 200}]
    if filters.tree_type == "Item":
        cols.append({"label": _("Item Name"),    "fieldname": "entity_name",  "fieldtype": "Data", "width": 180})
        cols.append({"label": _("Item Group"),   "fieldname": "item_group",   "fieldtype": "Data", "width": 130})
        cols.append({"label": _("Category"),     "fieldname": "category",     "fieldtype": "Data", "width": 120})
        cols.append({"label": _("Sub Category"), "fieldname": "sub_category", "fieldtype": "Data", "width": 130})
        cols.append({"label": _("Department"),   "fieldname": "department",   "fieldtype": "Data", "width": 120})
    elif filters.tree_type == "Customer":
        cols.append({"label": _("Customer Name"), "fieldname": "entity_name", "fieldtype": "Data", "width": 160})
    qty_label = "Transaksi" if filters.get("tree_type") in ("Customer", "Customer Group") else "Qty"
    for end_date in periodic_daterange:
        label = get_period_label(end_date, filters.range)
        cols.append({"label": _(label) + " (Rp)", "fieldname": scrub(label) + "_value", "fieldtype": "Currency", "width": 150})
        cols.append({"label": _(label) + " (" + qty_label + ")", "fieldname": scrub(label) + "_qty", "fieldtype": "Float", "width": 110})
    cols.append({"label": _("Total (Rp)"), "fieldname": "total_value", "fieldtype": "Currency", "width": 160})
    cols.append({"label": _("Total (" + qty_label + ")"), "fieldname": "total_qty", "fieldtype": "Float", "width": 120})
    return cols


def get_data(filters, periodic_daterange):
    cfg = TREE_TYPE_CONFIG.get(filters.tree_type, TREE_TYPE_CONFIG["Item Group"])
    entries = get_entries(filters, cfg)
    epd = frappe._dict()
    entity_names = {}
    entity_meta  = {}
    for e in entries:
        label = get_period_label(e.posting_date, filters.range)
        epd.setdefault(e.entity, frappe._dict())
        epd[e.entity].setdefault(scrub(label) + "_value", 0.0)
        epd[e.entity].setdefault(scrub(label) + "_qty",   0.0)
        epd[e.entity][scrub(label) + "_value"] += flt(e.value_field)
        epd[e.entity][scrub(label) + "_qty"]   += flt(e.qty_field)
        if e.get("entity_name"):
            entity_names.setdefault(e.entity, e.entity_name)
        if filters.tree_type == "Item" and e.entity not in entity_meta:
            entity_meta[e.entity] = {
                "item_group":   e.get("item_group") or "",
                "category":     e.get("category") or "",
                "sub_category": e.get("sub_category") or "",
                "department":   e.get("department") or "",
            }
    if cfg["is_group"]:
        return get_rows_by_group(filters, periodic_daterange, epd, cfg)
    else:
        return get_rows_flat(filters, periodic_daterange, epd, entity_names, entity_meta)


def get_entries(filters, cfg):
    conditions = []
    conditions.append("si.docstatus = 1")
    conditions.append("si.posting_date BETWEEN %(from_date)s AND %(to_date)s")
    conditions.append("si.company = %(company)s")
    conditions.append("si.is_return = 0")

    # Warehouse filter dengan support multi-select dan parent -> semua child
    wh_list = []
    warehouse_raw = filters.get("warehouses")
    if warehouse_raw:
        # Handle MultiSelectList (list of dicts atau list of strings)
        if isinstance(warehouse_raw, list):
            raw_list = []
            for w in warehouse_raw:
                if isinstance(w, dict):
                    raw_list.append(w.get("value") or w.get("name") or "")
                else:
                    raw_list.append(str(w))
            raw_list = [w for w in raw_list if w]
        else:
            raw_list = [str(warehouse_raw)]

        # Expand setiap warehouse ke children
        for wh in raw_list:
            children = get_warehouse_children(wh)
            for c in children:
                if c not in wh_list:
                    wh_list.append(c)

    if wh_list:
        if len(wh_list) == 1:
            wh_single = "'{}'".format(wh_list[0].replace("'","''"))
            conditions.append("sii.warehouse = {}".format(wh_single))
        else:
            wh_str = "({})".format(", ".join(["'{}'".format(w.replace("'","''")) for w in wh_list]))
            conditions.append("sii.warehouse IN {}".format(wh_str))

    # Filter outlet (si.custom_outlet). Dipakai langsung, BUKAN dipetakan ke
    # warehouse: MSHA dan XCW berbagi warehouse "SELLING AREA XCW - X" sehingga
    # pemetaan lewat warehouse akan menggabungkan dua outlet berbeda, dan
    # XSMGROW tidak punya warehouse sama sekali sehingga jadi tidak terfilter.
    outlet_list = get_outlet_list(filters)
    if outlet_list:
        conditions.append("si.custom_outlet IN %(outlet_list)s")
        filters.outlet_list = outlet_list

    if filters.get("item_code"):
        conditions.append("sii.item_code = %(item_code)s")
    if filters.get("item_group") and filters.tree_type not in ("Item Group", "Item"):
        conditions.append("i2.item_group = %(item_group)s")
    if filters.get("customer_group") and filters.tree_type != "Customer Group":
        conditions.append("si.customer_group = %(customer_group)s")
    if filters.get("territory") and filters.tree_type != "Territory":
        conditions.append("si.territory = %(territory)s")
    if filters.get("customer") and filters.tree_type != "Customer":
        conditions.append("si.customer = %(customer)s")
    if filters.get("category"):
        conditions.append("i_meta.category = %(category)s")
    if filters.get("sub_category"):
        conditions.append("i_meta.sub_category = %(sub_category)s")
    if filters.get("department"):
        conditions.append("i_meta.department = %(department)s")

    where = " AND ".join(conditions)
    entity_select = cfg["entity_field"] + " AS entity"
    extra_join = cfg["extra_join"]
    item_group_join = ""
    if filters.get("item_group") and filters.tree_type not in ("Item Group", "Item"):
        item_group_join = "JOIN `tabItem` i2 ON i2.name = sii.item_code"
    entity_name_select = ""
    if filters.tree_type == "Customer":
        entity_name_select = ", si.customer_name AS entity_name"
    elif filters.tree_type == "Item":
        entity_name_select = ", sii.item_name AS entity_name, i_meta.item_group, i_meta.category, i_meta.sub_category, i_meta.department"
    need_item_meta = (
        filters.tree_type == "Item"
        or filters.get("category")
        or filters.get("sub_category")
        or filters.get("department")
    )
    item_meta_join = "JOIN `tabItem` i_meta ON i_meta.name = sii.item_code" if need_item_meta else ""

    # Untuk Customer/Customer Group, qty_field = jumlah transaksi (invoice)
    if filters.tree_type in ("Customer", "Customer Group"):
        qty_select = "COUNT(DISTINCT si.name) AS qty_field"
    else:
        qty_select = "sii.qty AS qty_field"

    query = (
        "SELECT " + entity_select + entity_name_select + ", si.posting_date, sii.base_net_amount AS value_field, " + qty_select +
        " FROM `tabSales Invoice Item` sii"
        " JOIN `tabSales Invoice` si ON si.name = sii.parent"
        + (" " + extra_join if extra_join else "")
        + (" " + item_group_join if item_group_join else "")
        + (" " + item_meta_join if item_meta_join else "")
        + " WHERE " + where
    )

    # Untuk Customer/Customer Group - query khusus aggregate per customer per date
    if filters.tree_type in ("Customer", "Customer Group"):
        customer_query = (
            "SELECT " + cfg["entity_field"] + " AS entity, " + cfg["entity_field"] + " AS entity_name, si.posting_date,"
            " SUM(sii.base_net_amount) AS value_field, COUNT(DISTINCT si.name) AS qty_field"
            " FROM `tabSales Invoice Item` sii"
            " JOIN `tabSales Invoice` si ON si.name = sii.parent"
            + (" " + extra_join if extra_join else "")
            + " WHERE " + where
            + " GROUP BY " + cfg["entity_field"] + ", si.posting_date"
        )
        clean_filters2 = frappe._dict({k: v for k, v in filters.items() if k != "warehouses"})
        return frappe.db.sql(customer_query, clean_filters2, as_dict=True)

    # Bersihkan filter dari key warehouse kalau sudah di-inline
    clean_filters = frappe._dict({k: v for k, v in filters.items() if k != "warehouse" or len(wh_list) <= 1})
    return frappe.db.sql(query, clean_filters, as_dict=True)

def get_rows_flat(filters, periodic_daterange, epd, entity_names, entity_meta=None):
    if entity_meta is None:
        entity_meta = {}
    data = []
    for entity, period_data in epd.items():
        row = {"entity": entity, "entity_name": entity_names.get(entity), "indent": 0}
        if filters.tree_type == "Item":
            meta = entity_meta.get(entity, {})
            row["item_group"]   = meta.get("item_group", "")
            row["category"]     = meta.get("category", "")
            row["sub_category"] = meta.get("sub_category", "")
            row["department"]   = meta.get("department", "")
        total_value = 0.0
        total_qty   = 0.0
        for end_date in periodic_daterange:
            label = get_period_label(end_date, filters.range)
            val = flt(period_data.get(scrub(label) + "_value", 0.0))
            qty = flt(period_data.get(scrub(label) + "_qty", 0.0))
            row[scrub(label) + "_value"] = val
            row[scrub(label) + "_qty"]   = qty
            total_value += val
            total_qty   += qty
        # total_value dan total_qty sudah dihitung di loop
        row["total_value"] = total_value
        row["total_qty"]   = total_qty
        row["total"]       = total_value
        data.append(row)
    data.sort(key=lambda x: x["total"], reverse=True)
    return data


def get_rows_by_group(filters, periodic_daterange, epd, cfg):
    parent_field = cfg["parent_field"]
    tree_type    = filters.tree_type
    group_entries = frappe.db.sql(
        "SELECT name, lft, rgt, " + parent_field + " AS parent"
        " FROM `tab" + tree_type + "` ORDER BY lft",
        as_dict=True
    )
    depth_map = frappe._dict()
    for d in group_entries:
        if d.parent:
            depth_map[d.name] = depth_map.get(d.parent, 0) + 1
        else:
            depth_map[d.name] = 0
    out = []
    for d in reversed(group_entries):
        row = {"entity": d.name, "indent": depth_map.get(d.name, 0)}
        total_value = 0.0
        total_qty   = 0.0
        for end_date in periodic_daterange:
            label = get_period_label(end_date, filters.range)
            val = flt(epd.get(d.name, {}).get(scrub(label) + "_value", 0.0))
            qty = flt(epd.get(d.name, {}).get(scrub(label) + "_qty", 0.0))
            row[scrub(label) + "_value"] = val
            row[scrub(label) + "_qty"]   = qty
            if d.parent:
                epd.setdefault(d.parent, frappe._dict())
                epd[d.parent].setdefault(scrub(label) + "_value", 0.0)
                epd[d.parent].setdefault(scrub(label) + "_qty", 0.0)
                epd[d.parent][scrub(label) + "_value"] += val
                epd[d.parent][scrub(label) + "_qty"]   += qty
            total_value += val
            total_qty   += qty
        row["total_value"] = total_value
        row["total_qty"]   = total_qty
        row["total"]       = total_value
        out = [row, *out]
    return out


def get_chart_data(columns, data, filters):
    if not data: return None
    labels     = [c["label"] for c in columns if c["fieldname"] not in ("entity","entity_name","item_group","category","sub_category","department","total")]
    fieldnames = [c["fieldname"] for c in columns if c["fieldname"] not in ("entity","entity_name","item_group","category","sub_category","department","total")]
    cfg = TREE_TYPE_CONFIG.get(filters.tree_type, {})
    if cfg.get("is_group"):
        rows_to_chart = [r for r in data if r.get("indent", 0) == 0][:7]
    else:
        rows_to_chart = data[:7]
    datasets = []
    for row in rows_to_chart:
        datasets.append({"name": row.get("entity_name") or row.get("entity",""), "values": [flt(row.get(f,0)) for f in fieldnames]})
    return {"data": {"labels": labels, "datasets": datasets}, "type": "line", "fieldtype": "Currency"}
