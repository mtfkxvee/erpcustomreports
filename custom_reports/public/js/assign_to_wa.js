// Tambah checkbox "Kirim notifikasi via WhatsApp" di dialog Assign To (sidebar & bulk assign)
(function () {
	if (!frappe.ui.form.AssignToDialog) return;

	const original_get_fields = frappe.ui.form.AssignToDialog.prototype.get_fields;

	frappe.ui.form.AssignToDialog.prototype.get_fields = function () {
		const fields = original_get_fields.call(this);
		fields.push({
			fieldtype: "Check",
			fieldname: "send_wa",
			label: __("Kirim notifikasi via WhatsApp"),
			default: 0,
			description: __("Nomor WA diambil dari field \"Nomor WA\" di profil user yang ditugaskan."),
		});
		return fields;
	};
})();
