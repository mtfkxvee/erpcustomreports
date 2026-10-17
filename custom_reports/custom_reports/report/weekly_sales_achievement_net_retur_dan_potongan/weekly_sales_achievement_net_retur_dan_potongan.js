frappe.query_reports["Weekly Sales Achievement Net Retur dan Potongan"] = {
    filters: [
        {
            fieldname: "tanggal",
            label: __("Tanggal (minggu Senin-Minggu yg memuat tgl ini)"),
            fieldtype: "Date",
            default: frappe.datetime.add_days(frappe.datetime.get_today(), -7),
            reqd: 1
        }
    ],
    onload: function(report) {
        // Excel dgn tampilan spt file asli admin
        report.page.add_inner_button(__("Download Report"), function() {
            const tanggal = report.get_filter_value("tanggal");
            window.open(frappe.urllib.get_full_url(
                "/api/method/custom_reports.report_export.download_weekly_sales_net?tanggal=" + encodeURIComponent(tanggal)));
        });
    },
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
