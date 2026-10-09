from frappe.model.document import Document

from custom_reports.custom_reports.shelving.ledger import bin_name


class ShelvingBin(Document):
    """Saldo per (shelving, item). Hanya ditulis lewat shelving.ledger."""

    def autoname(self):
        self.name = bin_name(self.shelving, self.item_code)
