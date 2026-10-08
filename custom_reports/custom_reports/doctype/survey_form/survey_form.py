# Copyright (c) 2026, X-SHA and contributors
# For license information, please see license.txt

import re

import frappe
from frappe.model.document import Document

SLUG_RE = re.compile(r"^[A-Za-z0-9_-]+$")
PUBLIC_DOMAIN = "x-sha.id"


class SurveyForm(Document):
	def validate(self):
		if self.form_key:
			self.form_key = self.form_key.strip()

			if not SLUG_RE.match(self.form_key):
				frappe.throw(
					"URL Slug hanya boleh huruf, angka, tanda - dan _ (tanpa spasi/simbol lain)."
				)

			existing = frappe.db.get_value(
				"Survey Form", {"form_key": self.form_key, "name": ["!=", self.name or ""]}
			)
			if existing:
				frappe.throw(
					f'URL Slug "{self.form_key}" sudah dipakai survey lain ({existing}). Pilih slug lain.'
				)
		else:
			self.form_key = frappe.generate_hash(length=12)

		if self.status == "Published" and not self.questions:
			frappe.throw("Tambahkan minimal 1 pertanyaan sebelum survey di-Publish.")

		public_link = f"https://{PUBLIC_DOMAIN}/form/{self.form_key}"
		fallback_link = f"{frappe.utils.get_url()}/form/{self.form_key}"
		self.response_link_html = (
			f'<div style="padding:10px;background:#f5f5f5;border-radius:6px;">'
			f'<b>Link Responder:</b><br>'
			f'<a href="{public_link}" target="_blank">{public_link}</a><br>'
			f'<span style="font-size:12px;color:#888;">Fallback (selalu aktif): '
			f'<a href="{fallback_link}" target="_blank">{fallback_link}</a></span>'
			f'</div>'
		)
