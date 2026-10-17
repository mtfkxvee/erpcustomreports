const MM_BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli",
    "Agustus", "September", "Oktober", "November", "Desember"];

// Default = bulan lalu (laporan bulanan dibuat setelah bulannya selesai).
const MM_LALU = frappe.datetime.str_to_obj(frappe.datetime.add_months(frappe.datetime.get_today(), -1));

frappe.query_reports["Monthly Margin Target vs Achievement"] = {
    filters: [
        {
            fieldname: "bulan",
            label: __("Bulan"),
            fieldtype: "Select",
            options: MM_BULAN,
            default: MM_BULAN[MM_LALU.getMonth()],
            reqd: 1
        },
        {
            fieldname: "tahun",
            label: __("Tahun"),
            fieldtype: "Int",
            default: MM_LALU.getFullYear(),
            reqd: 1
        },
        {
            fieldname: "tampilan",
            label: __("Tampilan"),
            fieldtype: "Select",
            options: ["Ringkasan", "Rincian"],
            default: "Ringkasan",
            reqd: 1
        }
    ],
    onload: function(report) {
        if (!frappe.user.has_role("System Manager")) {
            return;
        }
        // Excel dgn tampilan spt file asli admin: SALES & MARGIN ACHV (Sheet1 ringkasan + Sheet4 rincian)
        report.page.add_inner_button(__("Download Report"), function() {
            const filters = JSON.stringify(report.get_values() || {});
            window.open(frappe.urllib.get_full_url(
                "/api/method/custom_reports.report_export.download_monthly_margin?filters=" + encodeURIComponent(filters)));
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
