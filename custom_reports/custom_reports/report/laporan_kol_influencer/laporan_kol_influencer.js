frappe.query_reports["Laporan KOL Influencer"] = {
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
			fieldname: "kol",
			label: __("KOL / Influencer"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe.db.get_link_options("Marketing KOL", txt);
			},
		},
		{
			fieldname: "platform",
			label: __("Platform"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe.call({
					method: "custom_reports.custom_reports.report.laporan_kol_influencer.laporan_kol_influencer.get_platforms",
					args: { txt: txt },
				}).then((r) => (r.message || []).map((row) => ({ value: row[0], description: "" })));
			},
		},
	],
};
