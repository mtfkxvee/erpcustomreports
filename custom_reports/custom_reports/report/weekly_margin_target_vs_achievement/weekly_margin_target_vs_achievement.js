frappe.query_reports["Weekly Margin Target vs Achievement"] = {
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
        if (!frappe.user.has_role("System Manager")) {
            return;
        }
        // Excel dgn tampilan spt file asli admin (header bertingkat, warna, format angka)
        report.page.add_inner_button(__("Download Report"), function() {
            const tanggal = report.get_filter_value("tanggal");
            window.open(frappe.urllib.get_full_url(
                "/api/method/custom_reports.report_export.download_weekly_margin?tanggal=" + encodeURIComponent(tanggal)));
        });
        report.page.add_inner_button(__("Ambil Ulang Snapshot"), function() {
            frappe.prompt(
                {
                    fieldname: "date",
                    label: __("Tanggal"),
                    fieldtype: "Date",
                    reqd: 1,
                    default: frappe.datetime.add_days(frappe.datetime.get_today(), -1)
                },
                function(values) {
                    frappe.confirm(
                        __("Snapshot penjualan & margin tanggal {0} akan dihitung ulang dari data ERP saat ini dan menggantikan angka yang tersimpan. Lanjutkan?",
                            [frappe.datetime.str_to_user(values.date)]),
                        function() {
                            frappe.call({
                                method: "custom_reports.sales_snapshot.retake_snapshot",
                                args: { date: values.date },
                                freeze: true,
                                freeze_message: __("Mengambil snapshot..."),
                                callback: function(r) {
                                    if (r.message) {
                                        frappe.show_alert({ message: __("Snapshot {0} tersimpan", [r.message.name]), indicator: "green" });
                                        report.refresh();
                                    }
                                }
                            });
                        }
                    );
                },
                __("Ambil Ulang Snapshot"),
                __("Ambil")
            );
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
