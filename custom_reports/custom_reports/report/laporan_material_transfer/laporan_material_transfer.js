frappe.query_reports["Laporan Material Transfer"] = {
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
            label: __("Warehouse (Asal)"),
            fieldtype: "Link",
            options: "Warehouse"
        },
        {
            fieldname: "target_warehouse",
            label: __("Target Warehouse (Tujuan)"),
            fieldtype: "Link",
            options: "Warehouse"
        },
        {
            fieldname: "item_code",
            label: __("Item"),
            fieldtype: "Link",
            options: "Item"
        },
        {
            fieldname: "item_group",
            label: __("Item Group"),
            fieldtype: "Link",
            options: "Item Group"
        },
        {
            fieldname: "brand",
            label: __("Brand"),
            fieldtype: "Link",
            options: "Brand"
        }
    ]
};
