import frappe
from frappe import _
from frappe.utils import flt, getdate, get_first_day, get_last_day, add_months
from frappe import scrub


def execute(filters=None):
    if not filters:
        filters = {}
    filters = frappe._dict(filters)
    if not filters.from_date or not filters.to_date:
        frappe.msgprint("Pilih periode terlebih dahulu.", indicator="orange", alert=True)
        return [], []

    report = PurchaseAnalytics(filters)
    return report.run()


class PurchaseAnalytics:
    def __init__(self, filters):
        self.filters = filters
        self.periodic_daterange = self.get_periodic_daterange()

    def run(self):
        self.get_columns()
        self.get_data()
        self.get_chart()
        return self.columns, self.data, None, self.chart

    def get_chart(self):
        if not self.data or len(self.data) < 2:
            self.chart = None
            return

        # Ambil top 5 entity (exclude grand total row)
        data_rows = [r for r in self.data if not str(r.get("entity","")).startswith("<b>")]
        top5 = data_rows[:5]

        labels = [self.get_period_label(d) for d in self.periodic_daterange]
        datasets = []
        for row in top5:
            values = [flt(row.get(scrub(self.get_period_label(d)), 0)) for d in self.periodic_daterange]
            datasets.append({
                "name": row.get("entity_name") or row.get("entity"),
                "values": values
            })

        self.chart = {
            "data": {
                "labels": labels,
                "datasets": datasets
            },
            "type": "bar",
            "fieldtype": "Currency" if self.filters.value_quantity == "Value" else "Float",
            "barOptions": {"stacked": 0},
            "axisOptions": {"xIsSeries": 1},
            "height": 300
        }

    def get_periodic_daterange(self):
        from_date = getdate(self.filters.from_date)
        to_date   = getdate(self.filters.to_date)
        ranges = []
        date = from_date
        while date <= to_date:
            if self.filters.range == "Weekly":
                end = date + frappe.utils.datetime.timedelta(days=6)
            elif self.filters.range == "Monthly":
                end = get_last_day(date)
            elif self.filters.range == "Quarterly":
                end = get_last_day(add_months(date, 2))
            else:
                end = getdate("{}-12-31".format(date.year))
            ranges.append(min(end, to_date))
            if self.filters.range == "Weekly":
                date = end + frappe.utils.datetime.timedelta(days=1)
            elif self.filters.range == "Monthly":
                date = add_months(get_first_day(date), 1)
            elif self.filters.range == "Quarterly":
                date = add_months(get_first_day(date), 3)
            else:
                date = getdate("{}-01-01".format(date.year + 1))
        return ranges

    def get_period_label(self, end_date):
        if self.filters.range == "Weekly":
            return "Week {}".format(end_date.strftime("%W %Y"))
        elif self.filters.range == "Monthly":
            return end_date.strftime("%b %Y")
        elif self.filters.range == "Quarterly":
            q = (end_date.month - 1) // 3 + 1
            return "Q{} {}".format(q, end_date.year)
        else:
            return str(end_date.year)

    def get_columns(self):
        tree_type = self.filters.tree_type
        self.columns = [
            {"label": _(tree_type), "fieldname": "entity", "fieldtype": "Data", "width": 200}
        ]
        if tree_type in ("Supplier", "Item"):
            self.columns.append({"label": _(tree_type + " Name"), "fieldname": "entity_name", "fieldtype": "Data", "width": 180})
        for end_date in self.periodic_daterange:
            label = self.get_period_label(end_date)
            ft = "Currency" if self.filters.value_quantity == "Value" else "Float"
            self.columns.append({"label": _(label), "fieldname": scrub(label), "fieldtype": ft, "width": 130})
        ft = "Currency" if self.filters.value_quantity == "Value" else "Float"
        self.columns.append({"label": _("Total"), "fieldname": "total", "fieldtype": ft, "width": 140})

    def get_data(self):
        self.entries = self.get_entries()
        self.entity_map = {}
        tree_type = self.filters.tree_type

        for e in self.entries:
            key = e.entity
            if key not in self.entity_map:
                self.entity_map[key] = {
                    "entity": key,
                    "entity_name": e.get("entity_name", key),
                }
                for end_date in self.periodic_daterange:
                    self.entity_map[key][scrub(self.get_period_label(end_date))] = 0.0
                self.entity_map[key]["total"] = 0.0

            period_key = scrub(self.get_period_label(e.posting_date))
            val = flt(e.value_field)
            if period_key in self.entity_map[key]:
                self.entity_map[key][period_key] += val
            self.entity_map[key]["total"] += val

        self.data = sorted(self.entity_map.values(), key=lambda x: x["total"], reverse=True)

        # Grand total row
        if self.data:
            grand = {"entity": "<b>Total</b>", "entity_name": "", "total": 0.0}
            for end_date in self.periodic_daterange:
                k = scrub(self.get_period_label(end_date))
                grand[k] = sum(r.get(k, 0) for r in self.data)
            grand["total"] = sum(r["total"] for r in self.data)
            self.data.append(grand)

    def get_entries(self):
        doc_type = self.filters.doc_type
        tree_type = self.filters.tree_type
        value_field = "base_net_amount" if self.filters.value_quantity == "Value" else "qty"
        warehouse = self.filters.get("warehouse")

        # Warehouse hierarchy
        wh_cond = ""
        if warehouse:
            wh = frappe.db.get_value("Warehouse", warehouse, ["lft", "rgt", "is_group"], as_dict=True)
            if wh and wh.is_group:
                wh_list = frappe.db.sql(
                    "SELECT name FROM `tabWarehouse` WHERE lft >= %s AND rgt <= %s AND is_group = 0",
                    (wh.lft, wh.rgt), as_dict=True
                )
                wh_names = [w.name for w in wh_list]
            else:
                wh_names = [warehouse]
            wh_str = ", ".join(["'{}'".format(w.replace("'","''")) for w in wh_names])
            wh_cond = "AND i.warehouse IN ({})".format(wh_str)

        # Entity field mapping
        if tree_type == "Supplier":
            entity_field = "p.supplier"
            entity_name_field = "p.supplier_name"
            join_item = True
        elif tree_type == "Supplier Group":
            entity_field = "sup.supplier_group"
            entity_name_field = "sup.supplier_group"
            join_item = True
        elif tree_type == "Item":
            entity_field = "i.item_code"
            entity_name_field = "i.item_name"
            join_item = True
        elif tree_type == "Item Group":
            entity_field = "item.item_group"
            entity_name_field = "item.item_group"
            join_item = True
        elif tree_type == "Warehouse":
            entity_field = "i.warehouse"
            entity_name_field = "i.warehouse"
            join_item = True
        else:
            entity_field = "p.supplier"
            entity_name_field = "p.supplier_name"
            join_item = True

        # Build query
        item_table = "`tab{} Item`".format(doc_type)
        parent_table = "`tab{}`".format(doc_type)

        extra_join = ""
        if tree_type == "Supplier Group":
            extra_join = "JOIN `tabSupplier` sup ON sup.name = p.supplier"

        sql = """
            SELECT {entity} AS entity,
                   {entity_name} AS entity_name,
                   p.posting_date,
                   SUM(i.{value_field}) AS value_field
            FROM {item_table} i
            JOIN {parent_table} p ON p.name = i.parent
            {extra_join}
            JOIN `tabItem` item ON item.name = i.item_code
            WHERE p.docstatus = 1
            AND p.posting_date BETWEEN %(from_date)s AND %(to_date)s
            AND p.company = %(company)s
            {wh_cond}
            GROUP BY {entity}, p.posting_date
            ORDER BY p.posting_date
        """.format(
            entity=entity_field,
            entity_name=entity_name_field,
            value_field=value_field,
            item_table=item_table,
            parent_table=parent_table,
            extra_join=extra_join,
            wh_cond=wh_cond,
        )

        return frappe.db.sql(sql, {
            "from_date": self.filters.from_date,
            "to_date":   self.filters.to_date,
            "company":   self.filters.get("company") or frappe.defaults.get_user_default("company"),
        }, as_dict=True)
