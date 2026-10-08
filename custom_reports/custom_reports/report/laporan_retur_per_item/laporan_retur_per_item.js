frappe.query_reports["Laporan Retur Per Item"] = {
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
        },
        {
            fieldname: "return_type",
            label: __("Jenis Retur"),
            fieldtype: "Select",
            options: "\nSales Return\nPurchase Return"
        },
        {
            fieldname: "warehouse",
            label: __("Source Warehouse"),
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
            fieldname: "customer",
            label: __("Customer"),
            fieldtype: "Link",
            options: "Customer"
        },
        {
            fieldname: "supplier",
            label: __("Supplier"),
            fieldtype: "Link",
            options: "Supplier"
        }
    ]
};
