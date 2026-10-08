frappe.query_reports["Laporan Penjualan Per Pelanggan"] = {
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
            fieldname: "mode",
            label: __("Tampilkan Per"),
            fieldtype: "Select",
            options: "Per Pelanggan\nPer Group Pelanggan",
            default: "Per Pelanggan",
            reqd: 1
        },
        {
            fieldname: "outlet",
            label: __("Outlet"),
            fieldtype: "MultiSelectList",
            get_data: function(txt) {
                return frappe.db.get_link_options("Outlet", txt);
            }
        },
        {
            fieldname: "customer",
            label: __("Pelanggan"),
            fieldtype: "Link",
            options: "Customer",
            depends_on: "eval:doc.mode == 'Per Pelanggan'"
        },
        {
            fieldname: "customer_group",
            label: __("Group Pelanggan"),
            fieldtype: "Link",
            options: "Customer Group",
            depends_on: "eval:doc.mode == 'Per Group Pelanggan'"
        }
    ]
};
