frappe.query_reports["Laporan Konten Media Sosial"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("Dari Tanggal"),
			fieldtype: "Date",
			default: frappe.datetime.month_start(),
		},
		{
			fieldname: "to_date",
			label: __("Sampai Tanggal"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "platform",
			label: __("Platform"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe.call({
					method: "custom_reports.custom_reports.report.laporan_konten_media_sosial.laporan_konten_media_sosial.get_platforms",
					args: { txt: txt },
				}).then((r) => (r.message || []).map((row) => ({ value: row[0], description: "" })));
			},
		},
		{
			fieldname: "account_name",
			label: __("Akun"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe.call({
					method: "custom_reports.custom_reports.report.laporan_konten_media_sosial.laporan_konten_media_sosial.get_accounts",
					args: { txt: txt },
				}).then((r) => (r.message || []).map((row) => ({ value: row[0], description: "" })));
			},
		},
	],
};
