frappe.query_reports["Laporan Kontribusi Item Group"] = {
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
            fieldname: "warehouse",
            label: __("Warehouse"),
            fieldtype: "Link",
            options: "Warehouse"
        },
        {
            fieldname: "item_group",
            label: __("Item Group"),
            fieldtype: "Link",
            options: "Item Group"
        },
        {
            fieldname: "department",
            label: __("Department"),
            fieldtype: "Data"
        },
        {
            fieldname: "category",
            label: __("Category"),
            fieldtype: "Data"
        },
        {
            fieldname: "sub_category",
            label: __("Sub Category"),
            fieldtype: "Data"
        }
    ]
};
