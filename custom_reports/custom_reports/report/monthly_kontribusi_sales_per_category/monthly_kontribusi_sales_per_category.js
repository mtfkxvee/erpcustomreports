const MKC_BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli",
    "Agustus", "September", "Oktober", "November", "Desember"];

// Default = bulan lalu (laporan bulanan dibuat setelah bulannya selesai).
const MKC_LALU = frappe.datetime.str_to_obj(frappe.datetime.add_months(frappe.datetime.get_today(), -1));

frappe.query_reports["Monthly Kontribusi Sales per Category"] = {
    filters: [
        {
            fieldname: "departemen",
            label: __("Departemen"),
            fieldtype: "Select",
            options: ["F&H.S", "FMCG", "XSL"],
            default: "F&H.S",
            reqd: 1
        },
        {
            fieldname: "bulan",
            label: __("Bulan"),
            fieldtype: "Select",
            options: MKC_BULAN,
            default: MKC_BULAN[MKC_LALU.getMonth()],
            reqd: 1
        },
        {
            fieldname: "tahun",
            label: __("Tahun"),
            fieldtype: "Int",
            default: MKC_LALU.getFullYear(),
            reqd: 1
        }
    ],
    onload: function(report) {
        if (!frappe.user.has_role("System Manager")) {
            return;
        }
        // Excel dgn tampilan spt file asli admin: KONTRIBUSI SALES CATEGORY (1 sheet per departemen)
        report.page.add_inner_button(__("Download Report"), function() {
            const filters = JSON.stringify(report.get_values() || {});
            window.open(frappe.urllib.get_full_url(
                "/api/method/custom_reports.report_export.download_monthly_kontribusi?filters=" + encodeURIComponent(filters)));
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
