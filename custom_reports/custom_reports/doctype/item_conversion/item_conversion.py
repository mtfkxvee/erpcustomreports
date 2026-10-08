import frappe
from frappe import _
from frappe.model.document import Document


class ItemConversion(Document):

    def validate(self):
        self.load_template_items()
        self.fetch_available_qty()
        self.fetch_current_stock()
        self.validate_total_qty()

    def load_template_items(self):
        if not self.template:
            return
        template = frappe.get_doc("Item Conversion Template", self.template)
        self.xsha_item = template.xsha_item
        if not self.conversion_items:
            for item in template.online_items:
                self.append("conversion_items", {
                    "online_item":  item.online_item,
                    "item_name":    item.item_name,
                    "variant_info": item.variant_info,
                    "total_qty":    0,
                    "current_qty":  0,
                    "uom":          item.uom,
                })

    def fetch_available_qty(self):
        if not self.xsha_item or not self.warehouse:
            self.available_qty = 0
            return
        qty = frappe.db.get_value(
            "Bin",
            {"item_code": self.xsha_item, "warehouse": self.warehouse},
            "actual_qty"
        ) or 0
        self.available_qty = float(qty)

    def fetch_current_stock(self):
        if not self.warehouse:
            return
        for row in self.conversion_items:
            current_qty = frappe.db.get_value(
                "Bin",
                {"item_code": row.online_item, "warehouse": self.warehouse},
                "actual_qty"
            ) or 0
            row.current_qty = float(current_qty)

    def validate_total_qty(self):
        if not self.xsha_qty:
            return
        total_allocated = sum(float(r.total_qty or 0) for r in self.conversion_items)
        xsha_qty = float(self.xsha_qty)
        if total_allocated > xsha_qty:
            frappe.throw(
                "Total qty yang dialokasikan ({}) melebihi Qty XSHA ({}).".format(
                    total_allocated, xsha_qty
                )
            )
        # Validasi stok XSHA tersedia
        if self.xsha_item and self.warehouse and xsha_qty > 0:
            available = frappe.db.get_value(
                "Bin",
                {"item_code": self.xsha_item, "warehouse": self.warehouse},
                "actual_qty"
            ) or 0
            available = float(available)
            if available < xsha_qty:
                frappe.msgprint(
                    "Peringatan: Stok item XSHA <b>{}</b> di warehouse <b>{}</b> "
                    "tidak mencukupi.<br>"
                    "Stok tersedia: <b>{}</b> | Qty yang dikonversi: <b>{}</b>".format(
                        self.xsha_item, self.warehouse, available, xsha_qty
                    ),
                    title="Stok Tidak Mencukupi",
                    indicator="orange"
                )

    def on_submit(self):
        if not self.expense_account:
            frappe.throw(_("Harap isi <b>Expense Account</b> terlebih dahulu."))
        total_allocated = sum(float(r.total_qty or 0) for r in self.conversion_items)
        if total_allocated == 0:
            frappe.throw(_("Total qty yang dialokasikan tidak boleh 0."))
        if total_allocated != float(self.xsha_qty or 0):
            frappe.throw(
                "Total qty ({}) harus sama dengan Qty XSHA ({}).".format(
                    total_allocated, self.xsha_qty
                )
            )
        self.create_stock_reconciliation()

    def create_stock_reconciliation(self):
        company = (
            frappe.defaults.get_user_default("company")
            or frappe.db.get_single_value("Global Defaults", "default_company")
        )
        sr = frappe.new_doc("Stock Reconciliation")
        sr.purpose          = "Stock Reconciliation"
        sr.posting_date     = self.conversion_date
        sr.company          = company
        sr.expense_account  = self.expense_account
        if self.cost_center:
            sr.cost_center  = self.cost_center

        def get_valuation_rate(item_code, warehouse):
            """Ambil valuation rate dari Bin atau Item master."""
            val_rate = frappe.db.get_value(
                "Bin",
                {"item_code": item_code, "warehouse": warehouse},
                "valuation_rate"
            ) or 0
            if not val_rate:
                val_rate = frappe.db.get_value("Item", item_code, "valuation_rate") or 0
            if not val_rate:
                # Ambil dari Stock Ledger Entry terakhir
                val_rate = frappe.db.sql(
                    "SELECT valuation_rate FROM `tabStock Ledger Entry`"
                    " WHERE item_code = %s AND is_cancelled = 0"
                    " ORDER BY posting_date DESC, posting_time DESC LIMIT 1",
                    item_code
                )
                val_rate = float(val_rate[0][0]) if val_rate else 0
            return float(val_rate)

        # Kurangi stok item XSHA
        current_xsha = frappe.db.get_value(
            "Bin",
            {"item_code": self.xsha_item, "warehouse": self.warehouse},
            "actual_qty"
        ) or 0
        new_xsha_qty = float(current_xsha) - float(self.xsha_qty)
        xsha_val_rate = get_valuation_rate(self.xsha_item, self.warehouse)
        sr.append("items", {
            "item_code":      self.xsha_item,
            "warehouse":      self.warehouse,
            "qty":            max(new_xsha_qty, 0),
            "valuation_rate": xsha_val_rate,
        })

        # Tambah stok item online
        for row in self.conversion_items:
            if float(row.total_qty or 0) <= 0:
                continue
            new_qty    = float(row.current_qty or 0) + float(row.total_qty or 0)
            val_rate   = get_valuation_rate(row.online_item, self.warehouse)
            if not val_rate:
                val_rate = xsha_val_rate  # fallback pakai valuation rate XSHA
            sr.append("items", {
                "item_code":      row.online_item,
                "warehouse":      self.warehouse,
                "qty":            new_qty,
                "valuation_rate": val_rate,
            })

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
