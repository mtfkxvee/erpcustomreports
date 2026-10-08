frappe.query_reports["Laporan Sales Promo"] = {
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
            fieldname: "warehouse",
            label: __("Warehouse"),
            fieldtype: "Link",
            options: "Warehouse"
        },
        {
            fieldname: "customer",
            label: __("Customer"),
            fieldtype: "Link",
            options: "Customer"
        },
        {
            fieldname: "item_code",
            label: __("Item"),
            fieldtype: "Link",
            options: "Item"
        },
        {
            fieldname: "pricing_rule",
            label: __("Pricing Rule"),
            fieldtype: "Data"
        }
    ]
};
