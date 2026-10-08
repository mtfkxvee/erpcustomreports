# Copyright (c) 2026, X-SHA and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class MarketingEvent(Document):
	def validate(self):
		if self.from_date and self.to_date and self.from_date > self.to_date:
			frappe.throw("Tanggal Mulai tidak boleh setelah Tanggal Selesai.")
