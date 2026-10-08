import frappe
from frappe import _
from frappe.model.document import Document


class ItemConversion(Document):

    def validate(self):
        self.load_template_items()
        self.calculate_quantities()

    def load_template_items(self):
        if not self.template:
            return
        template = frappe.get_doc("Item Conversion Template", self.template)
        self.xsha_item        = template.xsha_item
        self.source_warehouse = template.source_warehouse
        self.target_warehouse = template.target_warehouse
        if not self.conversion_items:
            for item in template.online_items:
                self.append("conversion_items", {
                    "online_item":  item.online_item,
                    "item_name":    item.item_name,
                    "variant_info": item.variant_info,
                    "qty_per_unit": item.qty_per_unit,
                    "uom":          item.uom,
                    "total_qty":    0,
                    "current_qty":  0,
                    "new_qty":      0,
                })

    def calculate_quantities(self):
        xsha_qty = float(self.xsha_qty or 0)
        for row in self.conversion_items:
            qty_per_unit  = float(row.qty_per_unit or 0)
            total_qty     = xsha_qty * qty_per_unit
            row.total_qty = total_qty
            current_qty   = frappe.db.get_value(
                "Bin",
                {"item_code": row.online_item, "warehouse": self.target_warehouse},
                "actual_qty"
            ) or 0
            row.current_qty = float(current_qty)
            row.new_qty     = row.current_qty + total_qty

    def on_submit(self):
        self.create_stock_reconciliation()

    def create_stock_reconciliation(self):
        if not self.conversion_items:
            frappe.throw(_("Tidak ada item untuk dikonversi."))
        company = frappe.defaults.get_user_default("company") or frappe.db.get_single_value("Global Defaults", "default_company")
        sr = frappe.new_doc("Stock Reconciliation")
        sr.purpose      = "Stock Reconciliation"
        sr.posting_date = self.conversion_date
        sr.company      = company
        for row in self.conversion_items:
            if float(row.new_qty or 0) < 0:
                continue
            sr.append("items", {
                "item_code": row.online_item,
                "warehouse": self.target_warehouse,
                "qty":       row.new_qty,
            })
        if not sr.items:
            frappe.throw(_("Tidak ada item yang bisa diproses."))
        sr.insert(ignore_permissions=True)
        sr.submit()
        self.db_set("stock_reconciliation", sr.name)
        frappe.msgprint(
            "Stock Reconciliation <b>{}</b> berhasil dibuat.".format(sr.name),
            indicator="green", alert=True
        )

    def on_cancel(self):
        if self.stock_reconciliation:
            sr = frappe.get_doc("Stock Reconciliation", self.stock_reconciliation)
            if sr.docstatus == 1:
                sr.cancel()
            frappe.msgprint(
                "Stock Reconciliation {} dibatalkan.".format(self.stock_reconciliation),
                alert=True
            )
