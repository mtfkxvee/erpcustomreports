// Copyright (c) 2026, X-SHA and contributors
// For license information, please see license.txt

frappe.ui.form.on("WhatsApp Blast", {
	refresh(frm) {
		if (!frm.is_new() && frm.doc.status !== "Sending") {
			frm.add_custom_button(__("Kirim Blast"), () => {
				frappe.confirm(
					__("Kirim pesan ke {0} penerima sekarang?", [frm.doc.recipients.length]),
					() => {
						frappe.call({
							doc: frm.doc,
							method: "send_blast",
							freeze: true,
							freeze_message: __("Mengirim blast..."),
							callback: (r) => {
								frm.reload_doc();
								if (r.message) {
									frappe.msgprint(
										__("Selesai: {0} terkirim, {1} gagal", [r.message.sent, r.message.failed])
									);
								}
							},
						});
					}
				);
			}).addClass("btn-primary");
		}

		if (!frm.is_new()) {
			frm.add_custom_button(__("Tambah dari Customer Group"), () => {
				let d = new frappe.ui.Dialog({
					title: __("Tambah Penerima dari Customer Group"),
					fields: [
						{
							fieldtype: "Link",
							fieldname: "customer_group",
							label: __("Customer Group"),
							options: "Customer Group",
							reqd: 1,
						},
					],
					primary_action_label: __("Tambah"),
					primary_action: (values) => {
						frappe.call({
							method: "custom_reports.custom_reports.doctype.whatsapp_blast.whatsapp_blast.get_recipients_from_customer_group",
							args: { customer_group: values.customer_group },
							callback: (r) => {
								(r.message || []).forEach((c) => {
									let exists = (frm.doc.recipients || []).some((row) => row.phone === c.phone);
									if (!exists) {
										let row = frm.add_child("recipients");
										row.phone = c.phone;
										row.recipient_name = c.recipient_name;
									}
								});
								frm.refresh_field("recipients");
								frappe.show_alert({
									message: __("{0} penerima ditambahkan", [(r.message || []).length]),
									indicator: "green",
								});
								d.hide();
							},
						});
					},
				});
				d.show();
			});
		}
	},
});
