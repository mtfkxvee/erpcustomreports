frappe.query_reports["Sales Analytics by Warehouse"] = {
	filters: [
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
			default: frappe.datetime.year_end(),
			reqd: 1,
		},
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "tree_type",
			label: __("Tree Type"),
			fieldtype: "Select",
			options: ["Item Group", "Item", "Customer", "Customer Group", "Territory", "Order Type", "Project"],
			default: "Item Group",
			reqd: 1,
		},
		{
			fieldname: "range",
			label: __("Range"),
			fieldtype: "Select",
			options: ["Weekly", "Monthly", "Quarterly", "Yearly"],
			default: "Monthly",
			reqd: 1,
		},
		{
			fieldname: "warehouses",
			label: __("Warehouse"),
			fieldtype: "MultiSelectList",
			get_data: function(txt) {
				return frappe.db.get_link_options("Warehouse", txt);
			}
		},
		{
			fieldname: "outlets",
			label: __("Outlet"),
			fieldtype: "MultiSelectList",
			get_data: function(txt) {
				return frappe.db.get_link_options("Outlet", txt);
			}
		},
		{
			fieldname: "item_group",
			label: __("Item Group"),
			fieldtype: "Link",
			options: "Item Group",
		},
		{
			fieldname: "item_code",
			label: __("Item"),
			fieldtype: "Link",
			options: "Item",
		},
		{
			fieldname: "customer_group",
			label: __("Customer Group"),
			fieldtype: "Link",
			options: "Customer Group",
		},
		{
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "Link",
			options: "Customer",
		},
		{
			fieldname: "territory",
			label: __("Territory"),
			fieldtype: "Link",
			options: "Territory",
		},
		{
			fieldname: "category",
			label: __("Category"),
			fieldtype: "Data",
		},
		{
			fieldname: "sub_category",
			label: __("Sub Category"),
			fieldtype: "Data",
		},
		{
			fieldname: "department",
			label: __("Department"),
			fieldtype: "Data",
		},
	],
};
