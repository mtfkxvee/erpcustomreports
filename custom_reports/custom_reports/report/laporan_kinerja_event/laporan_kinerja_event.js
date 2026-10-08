frappe.query_reports["Laporan Kinerja Event"] = {
	filters: [
		{
			fieldname: "marketing_event",
			label: __("Marketing Event"),
			fieldtype: "Link",
			options: "Marketing Event",
			reqd: 1,
		},
	],
};
