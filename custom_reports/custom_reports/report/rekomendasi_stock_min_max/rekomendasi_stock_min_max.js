const WARNA_STATUS = {
    "Habis": "red",
    "Perlu Order": "orange",
    "Aman": "green",
    "Overstock": "blue",
    "Tidak Laku": "gray",
    "Tidak Aktif": "gray"
};

frappe.query_reports["Rekomendasi Stock Min Max"] = {
    filters: [
        {
            fieldname: "warehouse",
            label: __("Warehouse"),
            fieldtype: "Link",
            options: "Warehouse",
            reqd: 1,
            get_query: function() {
                return { filters: { is_group: 0, disabled: 0 } };
            }
        },
        {
            fieldname: "from_date",
            label: __("Histori Dari"),
            fieldtype: "Date",
            default: frappe.datetime.add_months(frappe.datetime.get_today(), -3),
            reqd: 1
        },
        {
            fieldname: "to_date",
            label: __("Histori Sampai"),
            fieldtype: "Date",
            default: frappe.datetime.add_days(frappe.datetime.get_today(), -1),
            reqd: 1
        },
        {
            fieldname: "item_group",
            label: __("Item Group"),
            fieldtype: "Link",
            options: "Item Group"
        },
        {
            fieldname: "kelas",
            label: __("Kelas ABC"),
            fieldtype: "Select",
            options: ["", "A", "B", "C", "D"]
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: ["", "Habis", "Perlu Order", "Habis + Perlu Order", "Aman", "Overstock", "Tidak Laku", "Tidak Aktif"]
        },
        {
            fieldname: "sl_a",
            label: __("Service Level A (%)"),
            fieldtype: "Float",
            default: 98
        },
        {
            fieldname: "sl_b",
            label: __("Service Level B (%)"),
            fieldtype: "Float",
            default: 95
        },
        {
            fieldname: "sl_c",
            label: __("Service Level C (%)"),
            fieldtype: "Float",
            default: 90
        },
        {
            fieldname: "lt_transfer",
            label: __("Lead Time Transfer (hari)"),
            fieldtype: "Int",
            default: 3
        }
    ],
    formatter: function(value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        if (!data) {
            return value;
        }
        if (column.fieldname === "status" && data.status) {
            return `<span class="indicator-pill ${WARNA_STATUS[data.status] || "gray"}">${value}</span>`;
        }
        if (["safety_stock", "min_qty", "max_qty"].includes(column.fieldname)) {
            return `<b>${value}</b>`;
        }
        if (column.fieldname === "saran_order" && data.saran_order > 0) {
            return `<b style="color: var(--red-600)">${value}</b>`;
        }
        return value;
    }
};
