import frappe
from frappe.utils import add_to_date, now_datetime

RETENTION_DAYS = 30
BATCH_SIZE = 5000


def purge_old_logs():
	"""Insights Query Execution Log tidak punya retensi bawaan (Frappe versi ini
	tidak punya doctype 'Log Settings') dan ditulis ~13rb baris/hari terus-menerus,
	jadi dibersihkan manual di sini supaya tabel tidak tumbuh tanpa batas."""
	cutoff = add_to_date(now_datetime(), days=-RETENTION_DAYS)

	while True:
		frappe.db.sql(
			"DELETE FROM `tabInsights Query Execution Log` WHERE creation < %s LIMIT %s",
			(cutoff, BATCH_SIZE),
		)
		affected = frappe.db._cursor.rowcount
		frappe.db.commit()
		if affected < BATCH_SIZE:
			break
