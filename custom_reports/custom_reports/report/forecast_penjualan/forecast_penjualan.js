
frappe.query_reports["Forecast Penjualan"] = {
	filters: [
		{fieldname: "from_date", label: "Dari Tanggal", fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1},
		{fieldname: "to_date", label: "Sampai Tanggal", fieldtype: "Date", default: frappe.datetime.month_end(), reqd: 1},
		{
			fieldname: "outlet", label: "Outlet (kosong = semua)", fieldtype: "MultiSelectList",
			get_data: function (txt) { return frappe.db.get_link_options("Outlet", txt); }
		},
		{fieldname: "view", label: "Tampilan", fieldtype: "Select", options: "Harian\nTipe Hari\nPer Hari", default: "Harian"}
	],
	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldtype === "Percent" && data && data[column.fieldname] != null) {
			var v = data[column.fieldname];
			value = "<span style='color:" + (v < 0 ? "#c0392b" : "#1e8449") + "'>" + value + "</span>";
		}
		if (data && data.hari === "TOTAL") { value = "<b>" + value + "</b>"; }
		return value;
	}
};
