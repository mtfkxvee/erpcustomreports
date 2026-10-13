const WSA_BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli",
    "Agustus", "September", "Oktober", "November", "Desember"];

frappe.query_reports["Weekly Sales Achievement"] = {
    filters: [
        {
            fieldname: "bulan",
            label: __("Bulan"),
            fieldtype: "Select",
            options: WSA_BULAN,
            default: WSA_BULAN[frappe.datetime.str_to_obj(frappe.datetime.get_today()).getMonth()],
            reqd: 1
        },
        {
            fieldname: "tahun",
            label: __("Tahun"),
            fieldtype: "Int",
            default: frappe.datetime.str_to_obj(frappe.datetime.get_today()).getFullYear(),
            reqd: 1
        },
        {
            fieldname: "tampilan",
            label: __("Tampilan"),
            fieldtype: "Select",
            options: ["Mingguan", "Pembanding"],
            default: "Mingguan",
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
