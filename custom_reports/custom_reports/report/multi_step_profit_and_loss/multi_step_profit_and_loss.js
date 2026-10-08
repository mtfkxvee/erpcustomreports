// Multi Step Profit and Loss - Filter Configuration

function get_default_fiscal_year() {
    let fy = frappe.defaults.get_user_default("fiscal_year");
    if (!fy) {
        fy = String(new Date().getFullYear());
    }
    return fy;
}

frappe.query_reports["Multi Step Profit and Loss"] = {
    "filters": [
        {
            fieldname: "company",
            label: __("Company"),
            fieldtype: "Link",
            options: "Company",
            default: frappe.defaults.get_user_default("Company"),
            reqd: 1
        },
        {
            fieldname: "filter_based_on",
            label: __("Filter Based On"),
            fieldtype: "Select",
            options: ["Fiscal Year", "Date Range"],
            default: "Fiscal Year",
            reqd: 1,
            on_change: function() {
                let filter_based_on = frappe.query_report.get_filter_value('filter_based_on');
                frappe.query_report.toggle_filter_display('from_fiscal_year', filter_based_on === 'Date Range');
                frappe.query_report.toggle_filter_display('to_fiscal_year', filter_based_on === 'Date Range');
                frappe.query_report.toggle_filter_display('period_start_date', filter_based_on === 'Fiscal Year');
                frappe.query_report.toggle_filter_display('period_end_date', filter_based_on === 'Fiscal Year');
                frappe.query_report.refresh();
            }
        },
        {
            fieldname: "from_fiscal_year",
            label: __("Start Year"),
            fieldtype: "Link",
            options: "Fiscal Year",
            default: get_default_fiscal_year(),
            reqd: 1
        },
        {
            fieldname: "to_fiscal_year",
            label: __("End Year"),
            fieldtype: "Link",
            options: "Fiscal Year",
            default: get_default_fiscal_year(),
            reqd: 1
        },
        {
            fieldname: "period_start_date",
            label: __("Start Date"),
            fieldtype: "Date",
            default: frappe.datetime.year_start(),
            hidden: 1
        },
        {
            fieldname: "period_end_date",
            label: __("End Date"),
            fieldtype: "Date",
            default: frappe.datetime.get_today(),
            hidden: 1
        },
        {
            fieldname: "periodicity",
            label: __("Periodicity"),
            fieldtype: "Select",
            options: [
                { value: "Monthly", label: __("Monthly") },
                { value: "Quarterly", label: __("Quarterly") },
                { value: "Half-Yearly", label: __("Half-Yearly") },
                { value: "Yearly", label: __("Yearly") }
            ],
            default: "Yearly",
            reqd: 1
        },
        {
            fieldname: "finance_book",
            label: __("Finance Book"),
            fieldtype: "Link",
            options: "Finance Book"
        },
        {
            fieldname: "presentation_currency",
            label: __("Currency"),
            fieldtype: "Link",
            options: "Currency"
        },
        {
            fieldname: "cost_center",
            label: __("Cost Center"),
            fieldtype: "MultiSelectList",
            get_data: function(txt) {
                return frappe.db.get_link_options('Cost Center', txt, {
                    company: frappe.query_report.get_filter_value("company")
                });
            }
        },
        {
            fieldname: "project",
            label: __("Project"),
            fieldtype: "MultiSelectList",
            get_data: function(txt) {
                return frappe.db.get_link_options('Project', txt);
            }
        },
        {
            fieldname: "accumulated_values",
            label: __("Accumulated Values"),
            fieldtype: "Check"
        }
    ]
};
