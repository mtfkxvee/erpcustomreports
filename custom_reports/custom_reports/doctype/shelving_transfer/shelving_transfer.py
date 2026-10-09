import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from custom_reports.custom_reports.shelving.ledger import (
    get_default_shelving,
    post_entry,
    reverse_voucher,
)

PUTAWAY = "Put-away"
MOVE = "Pindah Shelving"
REMOVE = "Keluarkan dari Shelving"


class ShelvingTransfer(Document):

    def validate(self):
        if frappe.db.get_value("Warehouse", self.warehouse, "is_group"):
            frappe.throw(_("Warehouse {0} adalah group.").format(self.warehouse))
        if not self.items:
            frappe.throw(_("Isi minimal satu item."))
        for row in self.items:
            self.validate_row(row)

    def validate_row(self, row):
        if not frappe.get_cached_value("Item", row.item_code, "is_stock_item"):
            frappe.throw(_("Baris {0}: {1} bukan stock item.").format(row.idx, row.item_code))
        if flt(row.qty) <= 0:
            frappe.throw(_("Baris {0}: Qty harus lebih dari 0.").format(row.idx))

        # Put-away = dari rak BELUM DITATA; Keluarkan = kembali ke rak BELUM DITATA
        default = get_default_shelving(self.warehouse, create=True)
        if self.transfer_type == PUTAWAY:
            row.from_shelving = default
        elif self.transfer_type == REMOVE:
            row.to_shelving = default

        if self.transfer_type == MOVE and not row.from_shelving:
            frappe.throw(_("Baris {0}: isi Dari Shelving.").format(row.idx))
        if self.transfer_type in (PUTAWAY, MOVE) and not row.to_shelving:
            frappe.throw(_("Baris {0}: isi Ke Shelving.").format(row.idx))
        if self.transfer_type == REMOVE and not row.from_shelving:
            frappe.throw(_("Baris {0}: isi Dari Shelving.").format(row.idx))
        if self.transfer_type == MOVE and row.from_shelving == row.to_shelving:
            frappe.throw(_("Baris {0}: shelving asal dan tujuan sama.").format(row.idx))

        for fieldname in ("from_shelving", "to_shelving"):
            shelving = row.get(fieldname)
            if not shelving:
                continue
            wh, disabled = frappe.db.get_value("Shelving", shelving, ["warehouse", "disabled"])
            if wh != self.warehouse:
                frappe.throw(_("Baris {0}: shelving {1} bukan milik warehouse {2}.").format(
                    row.idx, shelving, self.warehouse))
            if disabled and fieldname == "to_shelving":
                frappe.throw(_("Baris {0}: shelving {1} nonaktif.").format(row.idx, shelving))

    def on_submit(self):
        for row in self.items:
            qty = flt(row.qty)
            args = (self.warehouse, row.item_code)
            meta = (self.doctype, self.name, row.name, self.posting_date, self.company)
            post_entry(row.from_shelving, *args, -qty, *meta)
            post_entry(row.to_shelving, *args, qty, *meta)

    def on_cancel(self):
        self.ignore_linked_doctypes = ("Shelving Ledger Entry",)
        reverse_voucher(self.doctype, self.name)
