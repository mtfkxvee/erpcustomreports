// urutan & nama sheet = file admin "SALES X-SHA GROUP_YTD_ 2026"
const YTD_SHEETS = ["TOTAL", "SLS & XMK", "XSL", "MBG", "XSC", "OSC", "PSR", "XPY", "XJB", "XCW", "OCW", "CIAWI ALL",
    "XSP", "OSP", "HCW", "DEPT.FHS", "XSM", "XMJ", "XWP", "XPH", "XTJ", "XCR", "TASMU", "MENARA", "GROW UIN", "GROW SP",
    "DEPT.FMCG", "DEPT.FMCG excl MBG", "TOTAL2", "HO (INCLUDE XOL)"];

frappe.query_reports["Sales YTD"] = {
    filters: [
        {
            fieldname: "sheet",
            label: __("Sheet"),
            fieldtype: "Select",
            options: YTD_SHEETS,
            default: "TOTAL",
            reqd: 1
        },
        {
            fieldname: "tahun",
            label: __("Sampai Tahun"),
            fieldtype: "Int",
            default: frappe.datetime.str_to_obj(frappe.datetime.get_today()).getFullYear(),
            reqd: 1
        }
    ],
    onload: function(report) {
        if (!frappe.user.has_role("System Manager")) {
            return;
        }
        // Excel dgn tampilan spt file asli admin: semua sheet (TOTAL, per outlet, per departemen)
        report.page.add_inner_button(__("Download Report"), function() {
            const filters = JSON.stringify(report.get_values() || {});
            window.open(frappe.urllib.get_full_url(
                "/api/method/custom_reports.report_export.download_sales_ytd?filters=" + encodeURIComponent(filters)));
        });
        report.page.add_inner_button(__("Ambil Ulang Bulan"), function() {
            const now = frappe.datetime.str_to_obj(frappe.datetime.add_months(frappe.datetime.get_today(), -1));
            frappe.prompt(
                [
                    { fieldname: "tahun", label: __("Tahun"), fieldtype: "Int", reqd: 1, default: now.getFullYear() },
                    { fieldname: "bulan", label: __("Bulan (1-12)"), fieldtype: "Int", reqd: 1, default: now.getMonth() + 1 }
                ],
                function(values) {
                    frappe.confirm(
                        __("Angka sales & target bulan {0}/{1} akan dihitung ulang dari data ERP saat ini. Bulan hasil import file YTD tidak diubah. Lanjutkan?",
                            [values.bulan, values.tahun]),
                        function() {
                            frappe.call({
                                method: "custom_reports.sales_ytd.refreeze_month",
                                args: values,
                                freeze: true,
                                callback: function(r) {
                                    if (r.message) {
                                        frappe.show_alert({ message: __("{0} baris tersimpan", [r.message.rows]), indicator: "green" });
                                        report.refresh();
                                    }
                                }
                            });
                        }
                    );
                },
                __("Ambil Ulang Bulan"),
                __("Ambil")
            );
        });
    },
    formatter: function(value, row, column, data, default_formatter) {
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
