import frappe
from frappe import _
from frappe.utils import formatdate, get_first_day, getdate

from tms.transport_management_system.api.driver_trip_monthly_report import (
	_build_captain_month_matrix,
	_get_history_lookups,
	_normalize_filters,
	_query_trip_rows,
)


def execute(filters=None):
	filters = filters or {}
	normalized = _prepare_filters(filters)
	lookups = _get_history_lookups()
	start_date = normalized.from_date if normalized.get("has_custom_range") else normalized.month_window_start
	rows = _query_trip_rows(normalized, start_date, normalized.to_date, lookups)
	matrix = _build_captain_month_matrix(rows, normalized)

	columns = [
		{"label": _("S.No"), "fieldname": "serial_no", "fieldtype": "Int", "width": 70},
		{"label": _("Captain"), "fieldname": "driver", "fieldtype": "Data", "width": 240},
		{"label": _("Vehicle"), "fieldname": "vehicle", "fieldtype": "Data", "width": 180},
		{"label": _("Created By"), "fieldname": "created_by_users", "fieldtype": "Data", "width": 160},
	]
	for month in matrix.get("months", []):
		columns.append(
			{
				"label": month.get("month_label"),
				"fieldname": month.get("month_key"),
				"fieldtype": "Int",
				"width": 100,
			}
		)
	columns.extend(
		[
			{"label": _("Active Months"), "fieldname": "active_months", "fieldtype": "Int", "width": 110},
			{"label": _("Total Trips"), "fieldname": "total_trips", "fieldtype": "Int", "width": 110},
		]
	)

	data = []
	for index, row in enumerate(matrix.get("rows", []), start=1):
		entry = {
			"serial_no": index,
			"driver": row.get("driver"),
			"vehicle": row.get("vehicle"),
			"created_by_users": row.get("created_by_users"),
			"active_months": row.get("active_months"),
			"total_trips": row.get("total_trips"),
		}
		for month, count in zip(matrix.get("months", []), row.get("counts", [])):
			entry[month.get("month_key")] = count
		data.append(entry)

	chart = {
		"data": {
			"labels": [month.get("month_label") for month in matrix.get("months", [])],
			"datasets": [{"name": _("Trips"), "values": matrix.get("totals", [])}],
		},
		"type": "bar",
		"height": 280,
	}
	report_summary = [
		{
			"label": _("Active Captains"),
			"value": matrix.get("summary", {}).get("active_drivers") or 0,
			"indicator": "Blue",
			"datatype": "Int",
		},
		{
			"label": _("Current Period Trips"),
			"value": matrix.get("summary", {}).get("current_month_total") or 0,
			"indicator": "Green",
			"datatype": "Int",
		},
		{
			"label": _("Rolling Total"),
			"value": matrix.get("summary", {}).get("rolling_total") or 0,
			"indicator": "Orange",
			"datatype": "Int",
		},
		{
			"label": _("Busiest Month"),
			"value": matrix.get("summary", {}).get("best_month_total") or 0,
			"indicator": "Gray",
			"datatype": "Int",
		},
	]
	return columns, data, None, chart, report_summary



def _prepare_filters(filters):
	normalized = _normalize_filters(
		company=filters.get("company"),
		month=filters.get("month"),
		driver=filters.get("driver"),
		include_cancelled=filters.get("include_cancelled"),
		months_span=filters.get("months_span"),
	)
	from_date = filters.get("from_date")
	to_date = filters.get("to_date")
	if from_date or to_date:
		start = getdate(from_date or to_date)
		end = getdate(to_date or from_date)
		if start > end:
			start, end = end, start
		normalized.from_date = start
		normalized.to_date = end
		normalized.month_date = end
		normalized.month_label = f"{formatdate(start, 'dd MMM yyyy')} - {formatdate(end, 'dd MMM yyyy')}"
		normalized.month_window_start = get_first_day(start)
		normalized.has_custom_range = 1
	else:
		normalized.has_custom_range = 0
	return normalized
