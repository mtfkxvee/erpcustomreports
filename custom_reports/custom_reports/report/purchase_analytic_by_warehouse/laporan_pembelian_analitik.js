frappe.query_reports["Laporan Pembelian Analitik"] = {
    filters: [
        {
            fieldname: "doc_type",
            label: __("Tipe Dokumen"),
            fieldtype: "Select",
            options: "Purchase Order\nPurchase Receipt\nPurchase Invoice",
            default: "Purchase Receipt",
            reqd: 1
        },
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
            fieldname: "tree_type",
            label: __("Berdasarkan"),
            fieldtype: "Select",
            options: "Supplier\nSupplier Group\nItem\nItem Group\nWarehouse",
            default: "Supplier",
            reqd: 1
        },
        {
            fieldname: "value_quantity",
            label: __("Nilai / Qty"),
            fieldtype: "Select",
            options: "Value\nQuantity",
            default: "Value"
        },
        {
            fieldname: "range",
            label: __("Periode"),
            fieldtype: "Select",
            options: "Weekly\nMonthly\nQuarterly\nYearly",
            default: "Monthly"
        },
        {
            fieldname: "warehouse",
            label: __("Warehouse"),
            fieldtype: "Link",
            options: "Warehouse"
        },
        {
            fieldname: "company",
            label: __("Company"),
            fieldtype: "Link",
            options: "Company",
            default: frappe.defaults.get_default("company")
        }
    ]
};
