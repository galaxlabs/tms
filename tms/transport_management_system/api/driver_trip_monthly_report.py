# Copyright (c) 2026, Galaxy Labs and contributors
# For license information, please see license.txt

from collections import OrderedDict

import frappe
from frappe.utils import add_to_date, cint, cstr, flt, formatdate, get_first_day, get_last_day, getdate, today


@frappe.whitelist()
def get_driver_trip_monthly_report(company=None, month=None, driver=None, include_cancelled=0, months_span=12):
	filters = _normalize_filters(
		company=company,
		month=month,
		driver=driver,
		include_cancelled=include_cancelled,
		months_span=months_span,
	)
	lookups = _get_history_lookups()
	currency = _get_currency(filters.company)

	current_rows = _query_trip_rows(filters, filters.from_date, filters.to_date, lookups)
	previous_filters = _build_previous_month_filters(filters)
	previous_rows = _query_trip_rows(previous_filters, previous_filters.from_date, previous_filters.to_date, lookups)
	count_window_rows = _query_trip_rows(filters, filters.month_window_start, filters.to_date, lookups)
	captain_month_matrix = _build_captain_month_matrix(count_window_rows, filters)

	summary = _build_summary(current_rows, filters)
	previous_summary = _build_summary(previous_rows, previous_filters)
	driver_summary = _build_driver_summary(current_rows)
	daily_activity = _build_daily_activity(current_rows, filters)
	status_breakdown = _build_status_breakdown(current_rows)
	top_routes = _build_route_summary(current_rows)
	insights = _build_insights(summary, previous_summary, driver_summary, top_routes, filters, captain_month_matrix)

	return {
		"filters": {
			"company": filters.company,
			"driver": filters.driver,
			"month": str(filters.month_date),
			"month_label": filters.month_label,
			"from_date": str(filters.from_date),
			"to_date": str(filters.to_date),
			"include_cancelled": cint(filters.include_cancelled),
			"months_span": cint(filters.months_span),
			"currency": currency,
		},
		"summary": summary,
		"previous_summary": previous_summary,
		"driver_summary": driver_summary,
		"daily_activity": daily_activity,
		"status_breakdown": status_breakdown,
		"top_routes": top_routes,
		"detail_rows": current_rows,
		"captain_month_matrix": captain_month_matrix,
		"insights": insights,
		"charts": {
			"daily_activity": _build_daily_activity_chart(daily_activity),
			"driver_ranking": _build_driver_ranking_chart(driver_summary),
			"status_distribution": _build_status_chart(status_breakdown),
		},
	}


def _normalize_filters(company=None, month=None, driver=None, include_cancelled=0, months_span=12):
	selected_date = _coerce_month_date(month)
	from_date = get_first_day(selected_date)
	to_date = get_last_day(selected_date)
	selected_company = (
		company
		or frappe.defaults.get_user_default("Company")
		or frappe.db.get_single_value("Global Defaults", "default_company")
	)
	selected_driver = cstr(driver or "").strip() or None
	span_value = max(3, min(cint(months_span or 12), 24))
	month_window_start = get_first_day(add_to_date(selected_date, months=-(span_value - 1)))
	return frappe._dict(
		company=selected_company,
		driver=selected_driver,
		month_date=selected_date,
		month_label=formatdate(selected_date, "MMMM yyyy"),
		from_date=from_date,
		to_date=to_date,
		include_cancelled=cint(include_cancelled),
		months_span=span_value,
		month_window_start=month_window_start,
	)


def _coerce_month_date(month):
	if not month:
		return getdate(today())

	month_value = cstr(month).strip()
	if len(month_value) == 7 and month_value.count("-") == 1:
		month_value = f"{month_value}-01"
	return getdate(month_value)


def _build_previous_month_filters(filters):
	previous_month_date = getdate(add_to_date(filters.month_date, months=-1))
	return frappe._dict(
		company=filters.company,
		driver=filters.driver,
		month_date=previous_month_date,
		month_label=formatdate(previous_month_date, "MMMM yyyy"),
		from_date=get_first_day(previous_month_date),
		to_date=get_last_day(previous_month_date),
		include_cancelled=filters.include_cancelled,
		months_span=filters.months_span,
		month_window_start=get_first_day(add_to_date(previous_month_date, months=-(filters.months_span - 1))),
	)


def _get_currency(company):
	if company:
		return frappe.db.get_value("Company", company, "default_currency")
	return frappe.db.get_single_value("Global Defaults", "default_currency") or "SAR"


def _get_history_lookups():
	staff_rows = frappe.get_all(
		"Staff",
		fields=["name", "company_name", "vehicle_assigned", "driver"],
		limit_page_length=0,
	)
	vehicle_rows = frappe.get_all(
		"Vehicle",
		fields=["name", "license_plate", "employee"],
		limit_page_length=0,
	)

	staff_by_exact = {}
	staff_by_normalized = {}
	vehicle_to_company = {}
	employee_ids = {row.get("employee") for row in vehicle_rows if row.get("employee")}
	employee_rows = frappe.get_all(
		"Employee",
		filters={"name": ["in", list(employee_ids)]} if employee_ids else None,
		fields=["name", "company", "employee_name"],
		limit_page_length=0,
	)
	employees_by_name = {row.get("name"): row for row in employee_rows if row.get("name")}

	for row in staff_rows:
		staff_doc = {
			"name": row.get("name") or "",
			"company_name": row.get("company_name") or "",
			"vehicle_assigned": row.get("vehicle_assigned") or "",
			"driver": row.get("driver") or "",
		}
		if staff_doc["name"]:
			staff_by_exact[staff_doc["name"]] = staff_doc
			staff_by_normalized[_normalize_person_key(staff_doc["name"])] = staff_doc
		if staff_doc["vehicle_assigned"] and staff_doc["company_name"]:
			vehicle_to_company[staff_doc["vehicle_assigned"]] = staff_doc["company_name"]

	for row in vehicle_rows:
		employee = employees_by_name.get(row.get("employee"))
		employee_company = employee.get("company") if employee else ""
		if not employee_company:
			continue

		vehicle_name = row.get("name") or ""
		license_plate = row.get("license_plate") or ""
		if vehicle_name and vehicle_name not in vehicle_to_company:
			vehicle_to_company[vehicle_name] = employee_company
		if license_plate and license_plate not in vehicle_to_company:
			vehicle_to_company[license_plate] = employee_company

	return frappe._dict(
		staff_by_exact=staff_by_exact,
		staff_by_normalized=staff_by_normalized,
		vehicle_to_company=vehicle_to_company,
	)


def _build_trip_conditions(filters, start_date, end_date):
	conditions = ["trip.docstatus < 2", "trip.date >= %(from_date)s", "trip.date <= %(to_date)s"]
	values = {
		"from_date": start_date,
		"to_date": end_date,
	}

	if filters.driver:
		conditions.append("trip.driver = %(driver)s")
		values["driver"] = filters.driver

	if not cint(filters.include_cancelled):
		conditions.append("COALESCE(trip.trip_status, '') != 'Cancelled'")

	return conditions, values


def _query_trip_rows(filters, start_date, end_date, lookups):
	conditions, values = _build_trip_conditions(filters, start_date, end_date)
	query = f"""
		SELECT
			trip.name,
			trip.owner,
			trip.creation,
			trip.modified,
			trip.date,
			trip.departure,
			trip.arrival,
			trip.driver,
			COALESCE(staff.company_name, '') AS exact_driver_company,
			COALESCE(staff.mobile_no, staff.phone, '') AS driver_mobile,
			COALESCE(staff.vehicle_assigned, '') AS exact_staff_vehicle,
			COALESCE(trip.assigned_vehicle, '') AS assigned_vehicle,
			COALESCE(trip.trip_route, '') AS trip_route,
			COALESCE(trip.from_location, '') AS from_location,
			COALESCE(trip.to_location, '') AS to_location,
			COALESCE(trip.trip_status, '') AS trip_status,
			COALESCE(trip.distance, 0) AS distance,
			COALESCE(trip.trip_value, 0) AS trip_value,
			COALESCE(trip.driver_commission_rate, 0) AS driver_commission_rate,
			COALESCE(trip.driver_commission_amount, 0) AS driver_commission_amount,
			COALESCE(trip.driver_share, 0) AS driver_share,
			COALESCE(trip.company_share, 0) AS company_share,
			COALESCE(trip.billing_mode, '') AS billing_mode,
			COALESCE(trip.vat_mode, '') AS vat_mode,
			COALESCE(trip.invoice_passenger_name, '') AS invoice_passenger_name,
			COALESCE(trip.invoice_passenger_mobile, '') AS invoice_passenger_mobile,
			COALESCE(trip.driver_commission_status, '') AS driver_commission_status
		FROM `tabTrip` trip
		LEFT JOIN `tabStaff` staff ON staff.name = trip.driver
		WHERE {' AND '.join(conditions)}
		ORDER BY trip.date ASC, trip.departure ASC, trip.name ASC
	"""
	raw_rows = frappe.db.sql(query, values, as_dict=True)
	rows = []

	for row in raw_rows:
		_resolve_trip_history(row, lookups)
		if filters.company and row.get("resolved_company") != filters.company:
			continue
		row.route_label = _get_route_label(row)
		row.trip_status = row.trip_status or "Unspecified"
		rows.append(row)

	return rows


def _resolve_trip_history(row, lookups):
	trip_driver = cstr(row.get("driver") or "").strip()
	trip_vehicle = cstr(row.get("assigned_vehicle") or row.get("exact_staff_vehicle") or "").strip()
	exact_company = cstr(row.get("exact_driver_company") or "").strip()
	matched_staff = lookups.staff_by_exact.get(trip_driver)
	if not matched_staff:
		matched_staff = lookups.staff_by_normalized.get(_normalize_person_key(trip_driver))

	row["resolved_driver"] = matched_staff.get("name") if matched_staff else (trip_driver or "Unassigned")
	row["resolved_company"] = (
		exact_company
		or (matched_staff.get("company_name") if matched_staff else "")
		or lookups.vehicle_to_company.get(trip_vehicle)
		or ""
	)
	row["resolved_vehicle"] = trip_vehicle or (matched_staff.get("vehicle_assigned") if matched_staff else "") or ""
	row["history_match_type"] = (
		"exact" if exact_company else "normalized" if matched_staff else "vehicle" if lookups.vehicle_to_company.get(trip_vehicle) else "trip_only"
	)
	row["created_by_user"] = cstr(row.get("owner") or "").strip()


def _normalize_person_key(value):
	return "".join(ch.lower() for ch in cstr(value or "") if ch.isalnum())


def _build_summary(rows, filters):
	trip_count = len(rows)
	active_days = len({cstr(row.date) for row in rows if row.get("date")})
	total_value = flt(sum(flt(row.trip_value) for row in rows))
	total_distance = flt(sum(flt(row.distance) for row in rows))
	total_commission = flt(sum(flt(row.driver_commission_amount) for row in rows))
	total_driver_share = flt(sum(flt(row.driver_share) for row in rows))
	total_company_share = flt(sum(flt(row.company_share) for row in rows))
	cancelled_count = len([row for row in rows if cstr(row.trip_status) == "Cancelled"])
	arrived_count = len([row for row in rows if cstr(row.trip_status) == "Arrived"])
	departed_count = len([row for row in rows if cstr(row.trip_status) == "Departed"])
	scheduled_count = len([row for row in rows if cstr(row.trip_status) == "Scheduled"])

	return {
		"trip_count": trip_count,
		"active_days": active_days,
		"total_value": total_value,
		"total_distance": total_distance,
		"total_commission": total_commission,
		"total_driver_share": total_driver_share,
		"total_company_share": total_company_share,
		"avg_trip_value": flt(total_value / trip_count) if trip_count else 0,
		"avg_distance": flt(total_distance / trip_count) if trip_count else 0,
		"arrived_count": arrived_count,
		"departed_count": departed_count,
		"scheduled_count": scheduled_count,
		"cancelled_count": cancelled_count,
		"completion_rate": flt((arrived_count / trip_count) * 100) if trip_count else 0,
		"cancellation_rate": flt((cancelled_count / trip_count) * 100) if trip_count else 0,
		"from_date": str(filters.from_date),
		"to_date": str(filters.to_date),
	}


def _build_driver_summary(rows):
	driver_map = OrderedDict()

	for row in rows:
		driver_key = row.get("resolved_driver") or row.driver or "Unassigned"
		bucket = driver_map.setdefault(
			driver_key,
			{
				"driver": driver_key,
				"driver_company": row.get("resolved_company") or "",
				"vehicles": set(),
				"created_by_users": set(),
				"trip_count": 0,
				"active_dates": set(),
				"total_value": 0.0,
				"total_distance": 0.0,
				"total_commission": 0.0,
				"total_driver_share": 0.0,
				"total_company_share": 0.0,
				"cancelled_count": 0,
			},
		)
		bucket["trip_count"] += 1
		if row.get("date"):
			bucket["active_dates"].add(cstr(row.date))
		if row.get("resolved_vehicle"):
			bucket["vehicles"].add(row.get("resolved_vehicle"))
		if row.get("created_by_user"):
			bucket["created_by_users"].add(row.get("created_by_user"))
		bucket["total_value"] += flt(row.trip_value)
		bucket["total_distance"] += flt(row.distance)
		bucket["total_commission"] += flt(row.driver_commission_amount)
		bucket["total_driver_share"] += flt(row.driver_share)
		bucket["total_company_share"] += flt(row.company_share)
		if cstr(row.trip_status) == "Cancelled":
			bucket["cancelled_count"] += 1

	rows_out = []
	for driver_key, data in driver_map.items():
		trip_count = data["trip_count"]
		rows_out.append(
			{
				"driver": driver_key,
				"driver_company": data["driver_company"],
				"vehicle": ", ".join(sorted(data["vehicles"])),
				"created_by_users": ", ".join(sorted(data["created_by_users"])),
				"trip_count": trip_count,
				"active_days": len(data["active_dates"]),
				"total_value": flt(data["total_value"]),
				"total_distance": flt(data["total_distance"]),
				"total_commission": flt(data["total_commission"]),
				"total_driver_share": flt(data["total_driver_share"]),
				"total_company_share": flt(data["total_company_share"]),
				"avg_trip_value": flt(data["total_value"] / trip_count) if trip_count else 0,
				"cancellation_rate": flt((data["cancelled_count"] / trip_count) * 100) if trip_count else 0,
			}
		)

	return sorted(rows_out, key=lambda row: (-flt(row["trip_count"]), -flt(row["total_value"]), row["driver"]))


def _build_daily_activity(rows, filters):
	day_map = OrderedDict()
	day_cursor = getdate(filters.from_date)
	day_end = getdate(filters.to_date)

	while day_cursor <= day_end:
		day_map[cstr(day_cursor)] = {
			"date": cstr(day_cursor),
			"label": formatdate(day_cursor, "dd MMM"),
			"trip_count": 0,
			"total_value": 0.0,
			"total_distance": 0.0,
		}
		day_cursor = getdate(add_to_date(day_cursor, days=1))

	for row in rows:
		key = cstr(row.date)
		if key not in day_map:
			continue
		day_map[key]["trip_count"] += 1
		day_map[key]["total_value"] += flt(row.trip_value)
		day_map[key]["total_distance"] += flt(row.distance)

	return [
		{
			"date": item["date"],
			"label": item["label"],
			"trip_count": item["trip_count"],
			"total_value": flt(item["total_value"]),
			"total_distance": flt(item["total_distance"]),
		}
		for item in day_map.values()
	]


def _build_status_breakdown(rows):
	status_map = OrderedDict()

	for row in rows:
		status = row.trip_status or "Unspecified"
		bucket = status_map.setdefault(status, {"status": status, "trip_count": 0, "total_value": 0.0})
		bucket["trip_count"] += 1
		bucket["total_value"] += flt(row.trip_value)

	return sorted(status_map.values(), key=lambda row: (-row["trip_count"], row["status"]))


def _build_route_summary(rows, limit=8):
	route_map = OrderedDict()

	for row in rows:
		route_label = _get_route_label(row)
		bucket = route_map.setdefault(route_label, {"route_label": route_label, "trip_count": 0, "total_value": 0.0})
		bucket["trip_count"] += 1
		bucket["total_value"] += flt(row.trip_value)

	return sorted(route_map.values(), key=lambda row: (-row["trip_count"], -row["total_value"], row["route_label"]))[:limit]


def _build_captain_month_matrix(rows, filters):
	months = []
	month_totals = OrderedDict()
	month_cursor = get_first_day(filters.month_window_start)
	month_end = get_first_day(filters.month_date)

	while month_cursor <= month_end:
		month_key = month_cursor.strftime("%Y-%m")
		months.append({
			"month_key": month_key,
			"month_label": formatdate(month_cursor, "MMM yyyy"),
		})
		month_totals[month_key] = 0
		month_cursor = getdate(add_to_date(month_cursor, months=1))

	driver_map = OrderedDict()
	for row in rows:
		driver_key = row.get("resolved_driver") or row.driver or "Unassigned"
		month_key = getdate(row.date).strftime("%Y-%m") if row.get("date") else None
		bucket = driver_map.setdefault(
			driver_key,
			{
				"driver": driver_key,
				"vehicle_set": set(),
				"created_by_set": set(),
				"counts": OrderedDict((m["month_key"], 0) for m in months),
			},
		)
		if row.get("resolved_vehicle"):
			bucket["vehicle_set"].add(row.get("resolved_vehicle"))
		if row.get("created_by_user"):
			bucket["created_by_set"].add(row.get("created_by_user"))
		if month_key in bucket["counts"]:
			bucket["counts"][month_key] += 1
			month_totals[month_key] = cint(month_totals.get(month_key, 0)) + 1

	rows_out = []
	for driver_key, bucket in driver_map.items():
		counts = [cint(bucket["counts"].get(month["month_key"], 0)) for month in months]
		rows_out.append({
			"driver": driver_key,
			"vehicle": ", ".join(sorted(bucket["vehicle_set"])),
			"created_by_users": ", ".join(sorted(bucket["created_by_set"])),
			"counts": counts,
			"active_months": len([count for count in counts if count]),
			"total_trips": sum(counts),
		})

	rows_out.sort(key=lambda row: (-row["total_trips"], row["driver"]))
	month_total_values = [cint(month_totals.get(month["month_key"], 0)) for month in months]
	best_month_total = max(month_total_values) if month_total_values else 0
	best_month_index = month_total_values.index(best_month_total) if month_total_values else 0
	best_month_label = months[best_month_index]["month_label"] if months else ""
	current_month_total = month_total_values[-1] if month_total_values else 0

	return {
		"months": months,
		"rows": rows_out,
		"totals": month_total_values,
		"grand_total": sum(month_total_values),
		"summary": {
			"active_drivers": len(rows_out),
			"current_month_total": current_month_total,
			"rolling_total": sum(month_total_values),
			"best_month_label": best_month_label,
			"best_month_total": best_month_total,
		},
	}


def _build_daily_activity_chart(daily_activity):
	return {
		"data": {
			"labels": [row["label"] for row in daily_activity],
			"datasets": [
				{"name": "Trips", "values": [row["trip_count"] for row in daily_activity]},
				{"name": "Value", "values": [flt(row["total_value"]) for row in daily_activity]},
			]
		},
		"type": "axis-mixed",
		"barOptions": {"stacked": 0},
		"height": 280,
	}


def _build_driver_ranking_chart(driver_summary):
	top_rows = driver_summary[:8]
	return {
		"data": {
			"labels": [row["driver"] for row in top_rows],
			"datasets": [{"name": "Trips", "values": [row["trip_count"] for row in top_rows]}],
		},
		"type": "bar",
		"height": 280,
	}


def _build_status_chart(status_breakdown):
	return {
		"data": {
			"labels": [row["status"] for row in status_breakdown],
			"datasets": [{"values": [row["trip_count"] for row in status_breakdown]}],
		},
		"type": "donut",
		"height": 280,
	}


def _build_insights(summary, previous_summary, driver_summary, top_routes, filters, captain_month_matrix):
	insights = []

	if not summary["trip_count"]:
		insights.append(
			f"No trips were found for {filters.month_label}. Adjust the driver or company filter to widen the view."
		)
		return insights

	if previous_summary["trip_count"]:
		change = summary["trip_count"] - previous_summary["trip_count"]
		if change > 0:
			insights.append(f"Trip volume is up by {change} compared with {previous_filters_label(filters)}.")
		elif change < 0:
			insights.append(f"Trip volume is down by {abs(change)} compared with {previous_filters_label(filters)}.")
		else:
			insights.append(f"Trip volume is flat compared with {previous_filters_label(filters)}.")

	top_driver = driver_summary[0] if driver_summary else None
	if top_driver:
		vehicle_text = f" using {top_driver['vehicle']}" if top_driver.get("vehicle") else ""
		insights.append(
			f"{top_driver['driver']} leads the month with {top_driver['trip_count']} trips{vehicle_text}."
		)

	top_route = top_routes[0] if top_routes else None
	if top_route:
		insights.append(
			f"Top route this month is {top_route['route_label']} with {top_route['trip_count']} trips."
		)

	count_summary = captain_month_matrix.get("summary") or {}
	if count_summary.get("best_month_total"):
		insights.append(
			f"The busiest month in the last {filters.months_span} months is {count_summary['best_month_label']} "
			f"with {count_summary['best_month_total']} trips."
		)

	if summary["cancellation_rate"] > 10:
		insights.append(
			f"Cancellation rate is {flt(summary['cancellation_rate']):.1f}%, which is high enough to review dispatch and driver readiness."
		)
	else:
		insights.append(
			f"Completion rate is {flt(summary['completion_rate']):.1f}% with {summary['arrived_count']} arrived trips."
		)

	return insights


def previous_filters_label(filters):
	previous_month_date = getdate(add_to_date(filters.month_date, months=-1))
	return formatdate(previous_month_date, "MMMM yyyy")


def _get_route_label(row):
	if row.get("trip_route"):
		return row.trip_route

	from_location = cstr(row.get("from_location") or "").strip()
	to_location = cstr(row.get("to_location") or "").strip()
	if from_location and to_location:
		return f"{from_location} -> {to_location}"
	if from_location or to_location:
		return from_location or to_location
	return "Unspecified Route"
