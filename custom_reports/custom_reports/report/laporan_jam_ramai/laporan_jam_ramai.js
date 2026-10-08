frappe.query_reports["Laporan Jam Ramai"] = {
    filters: [
        {
            fieldname: "from_date",
            label: __("Dari Tanggal"),
            fieldtype: "Date",
            default: frappe.datetime.month_start(),
            reqd: 1
        },
        {
            fieldname: "to_date",
            label: __("Sampai Tanggal"),
            fieldtype: "Date",
            default: frappe.datetime.get_today(),
            reqd: 1
        },
        {
            fieldname: "outlet",
            label: __("Outlet"),
            fieldtype: "MultiSelectList",
            get_data: function(txt) {
                return frappe.db.get_link_options("Outlet", txt);
            }
        }
    ]
};
