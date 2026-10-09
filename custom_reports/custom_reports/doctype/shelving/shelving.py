import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class Shelving(Document):

    def autoname(self):
        self.name = f"{(self.shelving_name or '').strip()} - {self.warehouse}"

    def before_insert(self):
        if not self.priority:
            last = frappe.db.sql(
                "select max(priority) from `tabShelving` where warehouse = %s and is_default = 0",
                self.warehouse)[0][0]
            self.priority = int(last or 0) + 1

    def validate(self):
        self.shelving_name = (self.shelving_name or "").strip()
        if frappe.db.get_value("Warehouse", self.warehouse, "is_group"):
            frappe.throw(_("Warehouse {0} adalah group, pilih warehouse yang bukan group.").format(
                self.warehouse))
        if not frappe.db.get_value("Warehouse", self.warehouse, "use_shelving"):
            frappe.throw(_("Warehouse {0} tidak diizinkan memakai shelving. Centang <b>Pakai "
                           "Shelving</b> di warehouse tersebut dulu.").format(self.warehouse))
        if self.is_default and self.disabled:
            frappe.throw(_("Rak bawaan tidak bisa dinonaktifkan."))
        if self.disabled and self.get_stock_qty():
            frappe.throw(_("Shelving {0} masih berisi stok, kosongkan dulu (Shelving Transfer "
                           "jenis Keluarkan) sebelum dinonaktifkan.").format(self.name))

    def after_insert(self):
        """Rak pertama di sebuah warehouse: buat rak bawaan, lalu masukkan seluruh stok warehouse
        yang ada ke rak bawaan di background (supaya rak = warehouse sejak awal).
        Rak berikutnya di warehouse yang sama tidak memicu apa pun."""
        if self.is_default:
            return
        from custom_reports.custom_reports.shelving.ledger import get_default_shelving
        if get_default_shelving(self.warehouse):
            return
        get_default_shelving(self.warehouse, create=True)
        frappe.enqueue("custom_reports.custom_reports.shelving.ledger.sync_warehouse",
                       warehouse=self.warehouse, queue="long", enqueue_after_commit=True)

    def get_stock_qty(self):
        return flt(frappe.db.sql(
            "select sum(actual_qty) from `tabShelving Bin` where shelving = %s", self.name)[0][0])

    def on_trash(self):
        if self.is_default and frappe.db.exists(
                "Shelving", {"warehouse": self.warehouse, "is_default": 0}):
            frappe.throw(_("Rak bawaan tidak bisa dihapus selama warehouse masih punya rak lain."))
        if frappe.db.exists("Shelving Ledger Entry", {"shelving": self.name}):
            frappe.throw(_("Shelving {0} sudah punya riwayat stok dan tidak bisa dihapus. "
                           "Nonaktifkan saja.").format(self.name))
        frappe.db.delete("Shelving Bin", {"shelving": self.name})
