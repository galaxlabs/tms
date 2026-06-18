import frappe
from frappe import _
from frappe.utils import add_to_date, date_diff, formatdate, get_first_day, get_last_day, getdate

from tms.transport_management_system.api.driver_trip_monthly_report import (
	_build_driver_ranking_chart,
	_build_previous_month_filters,
	_build_summary,
	_get_currency,
	_get_history_lookups,
	_normalize_filters,
	_query_trip_rows,
)


def execute(filters=None):
	filters = filters or {}
	normalized = _prepare_filters(filters)
	lookups = _get_history_lookups()
	currency = _get_currency(normalized.company)
	rows = _query_trip_rows(normalized, normalized.from_date, normalized.to_date, lookups)
	previous_filters = _prepare_previous_filters(normalized)
	previous_rows = _query_trip_rows(previous_filters, previous_filters.from_date, previous_filters.to_date, lookups)
	summary = _build_summary(rows, normalized)
	previous_summary = _build_summary(previous_rows, previous_filters)

	by_driver = {}
	for row in rows:
		key = row.get("resolved_driver") or row.get("driver") or _("Unassigned")
		entry = by_driver.setdefault(
			key,
			{
				"driver": key,
				"vehicle": set(),
				"created_by": set(),
				"driver_company": row.get("resolved_company") or row.get("exact_driver_company") or "",
				"trip_count": 0,
				"active_days": set(),
				"trip_value": 0.0,
				"distance": 0.0,
				"commission": 0.0,
				"driver_share": 0.0,
				"company_share": 0.0,
			},
		)
		if row.get("resolved_vehicle"):
			entry["vehicle"].add(row.get("resolved_vehicle"))
		if row.get("created_by_user"):
			entry["created_by"].add(row.get("created_by_user"))
		if row.get("date"):
			entry["active_days"].add(str(row.get("date")))
		entry["trip_count"] += 1
		entry["trip_value"] += float(row.get("trip_value") or 0)
		entry["distance"] += float(row.get("distance") or 0)
		entry["commission"] += float(row.get("driver_commission_amount") or 0)
		entry["driver_share"] += float(row.get("driver_share") or 0)
		entry["company_share"] += float(row.get("company_share") or 0)

	data = []
	for index, driver_name in enumerate(sorted(by_driver), start=1):
		entry = by_driver[driver_name]
		data.append(
			{
				"serial_no": index,
				"driver": entry["driver"],
				"vehicle": ", ".join(sorted(entry["vehicle"])),
				"created_by": ", ".join(sorted(entry["created_by"])),
				"driver_company": entry["driver_company"],
				"trip_count": entry["trip_count"],
				"active_days": len(entry["active_days"]),
				"trip_value": entry["trip_value"],
				"distance": entry["distance"],
				"commission": entry["commission"],
				"driver_share": entry["driver_share"],
				"company_share": entry["company_share"],
			}
		)

	chart = _build_driver_ranking_chart(
		[{"driver": row["driver"], "trip_count": row["trip_count"]} for row in data]
	)
	report_summary = [
		{
			"label": _("Total Trips"),
			"value": summary.get("trip_count") or 0,
			"indicator": "Blue",
			"datatype": "Int",
		},
		{
			"label": _("Trip Value"),
			"value": summary.get("total_value") or 0,
			"indicator": "Green",
			"datatype": "Currency",
			"currency": currency,
		},
		{
			"label": _("Distance"),
			"value": summary.get("total_distance") or 0,
			"indicator": "Orange",
			"datatype": "Float",
		},
		{
			"label": _("Previous Period Trips"),
			"value": previous_summary.get("trip_count") or 0,
			"indicator": "Gray",
			"datatype": "Int",
		},
	]
	return get_columns(currency), data, None, chart, report_summary



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



def _prepare_previous_filters(filters):
	if not filters.get("has_custom_range"):
		return _build_previous_month_filters(filters)

	span_days = date_diff(filters.to_date, filters.from_date)
	previous_to = getdate(add_to_date(filters.from_date, days=-1))
	previous_from = getdate(add_to_date(previous_to, days=-span_days))
	return frappe._dict(
		company=filters.company,
		driver=filters.driver,
		month_date=previous_to,
		month_label=f"{formatdate(previous_from, 'dd MMM yyyy')} - {formatdate(previous_to, 'dd MMM yyyy')}",
		from_date=previous_from,
		to_date=previous_to,
		include_cancelled=filters.include_cancelled,
		months_span=filters.months_span,
		month_window_start=get_first_day(previous_from),
		has_custom_range=1,
	)



def get_columns(currency):
	return [
		{"label": _("S.No"), "fieldname": "serial_no", "fieldtype": "Int", "width": 70},
		{"label": _("Driver"), "fieldname": "driver", "fieldtype": "Data", "width": 240},
		{"label": _("Vehicle"), "fieldname": "vehicle", "fieldtype": "Data", "width": 180},
		{"label": _("Created By"), "fieldname": "created_by", "fieldtype": "Data", "width": 160},
		{"label": _("Company"), "fieldname": "driver_company", "fieldtype": "Data", "width": 240},
		{"label": _("Trips"), "fieldname": "trip_count", "fieldtype": "Int", "width": 90},
		{"label": _("Active Days"), "fieldname": "active_days", "fieldtype": "Int", "width": 110},
		{"label": _("Trip Value"), "fieldname": "trip_value", "fieldtype": "Currency", "options": currency, "width": 130},
		{"label": _("Distance"), "fieldname": "distance", "fieldtype": "Float", "width": 120},
		{"label": _("Commission"), "fieldname": "commission", "fieldtype": "Currency", "options": currency, "width": 120},
		{"label": _("Driver Share"), "fieldname": "driver_share", "fieldtype": "Currency", "options": currency, "width": 130},
		{"label": _("Company Share"), "fieldname": "company_share", "fieldtype": "Currency", "options": currency, "width": 130},
	]
