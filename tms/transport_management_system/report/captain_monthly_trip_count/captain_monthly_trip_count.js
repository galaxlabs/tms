frappe.query_reports["Captain Monthly Trip Count"] = {
	onload(report) {
		report.page.add_inner_button(__("Driver Monthly Summary"), () => {
			frappe.set_route("query-report", "Driver Trip Monthly Summary");
		});
	},
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
			fieldname: "month",
			label: __("Month"),
			fieldtype: "Date",
			default: frappe.datetime.month_start(),
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
		},
		{
			fieldname: "driver",
			label: __("Driver"),
			fieldtype: "Data",
		},
		{
			fieldname: "include_cancelled",
			label: __("Include Cancelled"),
			fieldtype: "Check",
			default: 0,
		},
		{
			fieldname: "months_span",
			label: __("Count Window"),
			fieldtype: "Select",
			options: "6\n12\n18\n24",
			default: "12",
		},
	],
};
