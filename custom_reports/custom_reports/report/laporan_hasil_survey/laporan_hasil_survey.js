frappe.query_reports["Laporan Hasil Survey"] = {
	filters: [
		{
			fieldname: "survey_form",
			label: __("Survey Form"),
			fieldtype: "Link",
			options: "Survey Form",
			reqd: 1,
			get_query: () => ({ filters: { status: ["!=", "Draft"] } }),
		},
		{
			fieldname: "from_date",
			label: __("Dari Tanggal"),
			fieldtype: "Date",
		},
		{
			fieldname: "to_date",
			label: __("Sampai Tanggal"),
			fieldtype: "Date",
		},
		{
			fieldname: "question",
			label: __("Pertanyaan (untuk grafik distribusi)"),
			fieldtype: "Select",
			options: "",
		},
	],

	onload(report) {
		const survey_filter = report.get_filter("survey_form");
		if (survey_filter) {
			survey_filter.df.on_change = () => update_question_options(report);
		}
		update_question_options(report);
	},
};

function update_question_options(report) {
	const survey_form = report.get_filter_value("survey_form");
	const question_filter = report.get_filter("question");
	if (!question_filter) return;

	if (!survey_form) {
		question_filter.df.options = [""];
		question_filter.set_value("");
		question_filter.refresh();
		return;
	}

	frappe.call({
		method: "frappe.client.get_list",
		args: {
			doctype: "Survey Form Question",
			filters: { parent: survey_form, question_type: ["!=", "Section Break"] },
			fields: ["question"],
			order_by: "idx asc",
			limit_page_length: 0,
		},
		callback: (r) => {
			const options = [""].concat((r.message || []).map((q) => q.question));
			question_filter.df.options = options.join("\n");
			question_filter.refresh();
		},
	});
}
