frappe.query_reports["Laporan Sales Per Supplier"] = {
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
            fieldname: "supplier",
            label: __("Supplier"),
            fieldtype: "Link",
            options: "Supplier"
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
        }
    ],
    get_datatable_options(options) {
        return Object.assign(options, {
            checkboxColumn: false,
            dynamicRowHeight: false,
        });
    },
    after_datatable_render(datatable) {
        // Force re-render untuk kolom dinamis
        datatable.style.setStyle(".dt-cell", { "white-space": "nowrap" });
    }
};
