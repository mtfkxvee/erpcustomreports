const WVA_BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli",
    "Agustus", "September", "Oktober", "November", "Desember"];

frappe.query_reports["Weekly Visitor TC AC Achievement"] = {
    filters: [
        {
            fieldname: "bulan",
            label: __("Bulan"),
            fieldtype: "Select",
            options: WVA_BULAN,
            default: WVA_BULAN[frappe.datetime.str_to_obj(frappe.datetime.get_today()).getMonth()],
            reqd: 1
        },
        {
            fieldname: "tahun",
            label: __("Tahun"),
            fieldtype: "Int",
            default: frappe.datetime.str_to_obj(frappe.datetime.get_today()).getFullYear(),
            reqd: 1
        }
    ],
    formatter: function(value, row, column, data, default_formatter) {
        // angka 0 tampil "-" spt format akuntansi di laporan Excel asli
        if (["Int", "Float", "Currency", "Percent"].includes(column.fieldtype) && value === 0) {
            value = '<div style="text-align: right">-</div>';
        } else {
            value = default_formatter(value, row, column, data);
        }
        if (data && data.bold) {
            value = value.bold();
        }
        return value;
    }
};
