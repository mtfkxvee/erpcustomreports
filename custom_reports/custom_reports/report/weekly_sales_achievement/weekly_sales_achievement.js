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
            fieldname: "sampai_tanggal",
            label: __("Sampai Tanggal (opsional)"),
            fieldtype: "Date",
            description: __("Kosongkan utk minggu penuh. Isi mis. tgl 4 kalau laporan dibuat Senin tgl 5 (bulan terpilih dihitung s/d tgl ini).")
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
