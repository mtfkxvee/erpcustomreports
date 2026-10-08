frappe.query_reports["General Ledger X-SHA"] = {
    filters: [
        {
            fieldname: "company",
            label: __("Company"),
            fieldtype: "Link",
            options: "Company",
            default: frappe.defaults.get_user_default("Company"),
            reqd: 1,
        },
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            default: frappe.datetime.year_start(),
            reqd: 1,
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            default: frappe.datetime.get_today(),
            reqd: 1,
        },
        {
            fieldname: "account",
            label: __("Account"),
            fieldtype: "MultiSelectList",
            get_data: function(txt) {
                return frappe.db.get_link_options("Account", txt, {company: frappe.query_report.get_filter_value("company")});
            },
        },
        {
            fieldname: "cost_center",
            label: __("Cost Center"),
            fieldtype: "MultiSelectList",
            get_data: function(txt) {
                return frappe.db.get_link_options("Cost Center", txt, {company: frappe.query_report.get_filter_value("company")});
            },
        },
        {
            fieldname: "voucher_no",
            label: __("Voucher No"),
            fieldtype: "Data",
        },
        {
            fieldname: "party_type",
            label: __("Party Type"),
            fieldtype: "Link",
            options: "Party Type",
        },
        {
            fieldname: "party",
            label: __("Party"),
            fieldtype: "MultiSelectList",
            get_data: function(txt) {
                if (!frappe.query_report.get_filter_value("party_type")) return;
                return frappe.db.get_link_options(
                    frappe.query_report.get_filter_value("party_type"), txt
                );
            },
        },
        {
            fieldname: "project",
            label: __("Project"),
            fieldtype: "MultiSelectList",
            get_data: function(txt) {
                return frappe.db.get_link_options("Project", txt);
            },
        },
        {
            fieldname: "categorize_by",
            label: __("Categorize By"),
            fieldtype: "Select",
            options: [
                "",
                "Categorize by Account",
                "Categorize by Party",
                "Categorize by Voucher",
                "Categorize by Voucher (Consolidated)",
            ],
            default: "",
        },
        {
            fieldname: "show_opening_entries",
            label: __("Show Opening Entries"),
            fieldtype: "Check",
        },
        {
            fieldname: "include_default_book_entries",
            label: __("Include Default Book Entries"),
            fieldtype: "Check",
            default: 1,
        },
        {
            fieldname: "show_net_values_in_party_account",
            label: __("Show Net Values in Party Account"),
            fieldtype: "Check",
        },
        {
            fieldname: "add_values_in_transaction_currency",
            label: __("Show transaction currency"),
            fieldtype: "Check",
        },
    ],
    formatter: function(value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        if (data && data.bold) {
            value = value.bold();
        }
        return value;
    },
};
