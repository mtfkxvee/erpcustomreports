frappe.query_reports["Stok per Shelving"] = {
    filters: [
        { fieldname: "warehouse", label: __("Warehouse"), fieldtype: "Link", options: "Warehouse" },
        {
            fieldname: "shelving", label: __("Shelving"), fieldtype: "Link", options: "Shelving",
            get_query: () => {
                const wh = frappe.query_report.get_filter_value("warehouse");
                return { filters: wh ? { warehouse: wh } : {} };
            },
        },
        { fieldname: "item_code", label: __("Item"), fieldtype: "Link", options: "Item" },
    ],
};
