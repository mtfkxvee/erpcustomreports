frappe.query_reports["Laporan Cancel"] = {
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
            fieldname: "doctype",
            label: __("Tipe Dokumen"),
            fieldtype: "Select",
            options: "\nSales Invoice\nPurchase Invoice\nPurchase Receipt\nStock Entry\nStock Reconciliation",
            default: ""
        },
        {
            fieldname: "warehouse",
            label: __("Warehouse"),
            fieldtype: "Link",
            options: "Warehouse"
        }
    ]
};
