// Copyright (c) 2026, X-SHA and contributors
// For license information, please see license.txt

frappe.ui.form.on("Survey Form", {
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Lihat Response"), () => {
				frappe.set_route("List", "Survey Form Response", { survey_form: frm.doc.name });
			});

			if (frm.doc.form_key) {
				const link = `https://x-sha.id/form/${frm.doc.form_key}`;
				frm.add_custom_button(__("Copy Link Responder"), () => {
					frappe.utils.copy_to_clipboard(link);
					frappe.show_alert({ message: __("Link disalin"), indicator: "green" });
				});
			}
		}
	},
});
