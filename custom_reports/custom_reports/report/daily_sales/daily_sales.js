const DS_BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli",
    "Agustus", "September", "Oktober", "November", "Desember"];
const DS_NOW = frappe.datetime.str_to_obj(frappe.datetime.get_today());

frappe.query_reports["Daily Sales"] = {
    filters: [
        {
            fieldname: "bulan",
            label: __("Bulan"),
            fieldtype: "Select",
            options: DS_BULAN,
            default: DS_BULAN[DS_NOW.getMonth()],
            reqd: 1
        },
        {
            fieldname: "tahun",
            label: __("Tahun"),
            fieldtype: "Int",
            default: DS_NOW.getFullYear(),
            reqd: 1
        }
    ],
    onload: function(report) {
        if (!frappe.user.has_role("System Manager")) {
            return;
        }
        // Excel dgn tampilan spt sheet "Daily sales" file SALES REPORT HO (termasuk tabel rata2 per hari)
        report.page.add_inner_button(__("Download Report"), function() {
            const filters = JSON.stringify(report.get_values() || {});
            window.open(frappe.urllib.get_full_url(
                "/api/method/custom_reports.report_export.download_daily_sales?filters=" + encodeURIComponent(filters)));
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
