frappe.query_reports["Daily Inventory"] = {
    filters: [
        {
            fieldname: "from_date",
            label: __("Dari Tanggal"),
            fieldtype: "Date",
            default: frappe.datetime.get_today(),
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
            fieldname: "variant",
            label: __("Varian"),
            fieldtype: "Select",
            options: ["ALL", "EXC TOPUP", "EXC TOPUP&SEM"],
            default: "ALL",
            reqd: 1
        }
    ],
    formatter: function(value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        if (data && data.bold) {
            value = value.bold();
        }
        return value;
    }
};
