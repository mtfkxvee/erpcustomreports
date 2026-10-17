const KSC_BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli",
    "Agustus", "September", "Oktober", "November", "Desember"];

// Default = minggu (blok 1-7/8-14/15-21/22-akhir) terakhir yg sudah selesai.
function ksc_default_week() {
    const d = frappe.datetime.str_to_obj(frappe.datetime.add_days(frappe.datetime.get_today(), -1));
    const last_day = new Date(d.getFullYear(), d.getMonth() + 1, 0).getDate();
    const ends = [7, 14, 21, last_day];
    let idx = ends.findIndex(e => d.getDate() <= e);
    let month = d.getMonth(), year = d.getFullYear();
    if (d.getDate() !== ends[idx]) {
        idx -= 1;  // blok yg memuat kemarin blm selesai -> pakai blok sebelumnya
        if (idx < 0) {
            idx = 3;
            month -= 1;
            if (month < 0) { month = 11; year -= 1; }
        }
    }
    return {bulan: KSC_BULAN[month], tahun: year, minggu: "W" + (idx + 1)};
}

const KSC_DEFAULT = ksc_default_week();

frappe.query_reports["Weekly Kontribusi Sales per Category"] = {
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
            options: KSC_BULAN,
            default: KSC_DEFAULT.bulan,
            reqd: 1
        },
        {
            fieldname: "tahun",
            label: __("Tahun"),
            fieldtype: "Int",
            default: KSC_DEFAULT.tahun,
            reqd: 1
        },
        {
            fieldname: "minggu",
            label: __("Minggu (vs minggu sebelumnya)"),
            fieldtype: "Select",
            options: ["W1", "W2", "W3", "W4"],
            default: KSC_DEFAULT.minggu,
            reqd: 1
        },
        {
            fieldname: "sampai_tanggal",
            label: __("Sampai Tanggal (opsional)"),
            fieldtype: "Date",
            description: __("Kosongkan utk minggu penuh. Isi mis. tgl 4 kalau laporan dibuat Senin tgl 5 (minggu ini dihitung s/d tgl ini, minggu pembanding tetap penuh).")
        }
    ],
    onload: function(report) {
        // Excel dgn tampilan spt file asli admin
        report.page.add_inner_button(__("Download Report"), function() {
            const filters = JSON.stringify(report.get_values() || {});
            window.open(frappe.urllib.get_full_url(
                "/api/method/custom_reports.report_export.download_kontribusi?filters=" + encodeURIComponent(filters)));
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
