# Copyright (c) 2026, Galaxy Labs and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import getdate, get_first_day, get_last_day, now_datetime, add_to_date, flt, formatdate
from frappe.query_builder import DocType
from frappe.query_builder.functions import Sum, Count, Coalesce


@frappe.whitelist()
def get_dashboard_data(
	month=None, driver=None, period="monthly",
	dimension="driver", metric="vat",
	from_date=None, to_date=None,
):
	"""Multi-dimension analytics dashboard — slice by driver, date, or route."""

	year = now_datetime().year
	months_list = [
		"January", "February", "March", "April", "May", "June",
		"July", "August", "September", "October", "November", "December",
	]

	if from_date and to_date:
		start_date = getdate(from_date)
		end_date = getdate(to_date)
	else:
		if not month:
			month = now_datetime().strftime("%B")
		try:
			month_index = months_list.index(month) + 1
		except ValueError:
			month_index = now_datetime().month
		start_date = getdate(f"{year}-{month_index:02d}-01")
		end_date = get_last_day(start_date)

	driver = str(driver).strip() if driver else None
	period = period or "monthly"
	dimension = dimension or "driver"
	metric = metric or "vat"

	base_filters = {
		"start_date": start_date,
		"end_date": end_date,
		"driver": driver,
	}

	summary = _get_summary(base_filters)
	chart_data = _get_chart_data(base_filters, period, dimension, metric)
	pivot = _get_pivot_data(base_filters, period, dimension, metric)
	driver_breakdown = _get_driver_breakdown(base_filters)
	top_routes = _get_route_breakdown(base_filters)
	daily_breakdown = _get_daily_breakdown(base_filters) if period == "daily" else []
	weekly_breakdown = _get_weekly_breakdown(base_filters) if period == "weekly" else []
	invoice_list = _get_invoice_list(base_filters)
	drivers_list = _get_drivers_list(start_date, end_date)

	return {
		"summary": summary,
		"chart_data": chart_data,
		"pivot": pivot,
		"driver_breakdown": driver_breakdown,
		"top_routes": top_routes,
		"daily_breakdown": daily_breakdown,
		"weekly_breakdown": weekly_breakdown,
		"invoices": invoice_list,
		"drivers": drivers_list,
		"filters": {
			"from_date": str(start_date),
			"to_date": str(end_date),
			"month_label": formatdate(start_date, "MMMM yyyy"),
			"driver": driver or "",
			"period": period,
			"dimension": dimension,
			"metric": metric,
		},
	}


def _get_summary(filters):
	TI = DocType("Trip Invoice")
	T = DocType("Trip")

	q = (
		frappe.qb.from_(TI)
		.left_join(T).on(TI.trip == T.name)
		.select(
			Count(TI.name).as_("total_trips"),
			Coalesce(Sum(T.distance), 0).as_("total_distance"),
			Coalesce(Sum(T.trip_value), 0).as_("total_trip_value"),
			Coalesce(Sum(TI.net_total), 0).as_("total_net"),
			Coalesce(Sum(TI.vat_amount), 0).as_("total_vat"),
			Coalesce(Sum(TI.grand_total), 0).as_("grand_total"),
		)
		.where(TI.docstatus.lt(2))
		.where(TI.invoice_date >= filters["start_date"])
		.where(TI.invoice_date <= filters["end_date"])
	)
	if filters["driver"]:
		q = q.where(T.driver == filters["driver"])

	row = q.run(as_dict=True)
	row = row[0] if row else {}

	total_vat = flt(row.get("total_vat", 0))
	total_trip_value = flt(row.get("total_trip_value", 0))
	total_net = flt(row.get("total_net", 0))
	total_grand = flt(row.get("grand_total", 0))
	total_trips = row.get("total_trips", 0) or 0

	avg_per_trip = flt(total_grand / total_trips) if total_trips else 0
	vat_of_trip_pct = flt((total_vat / total_trip_value) * 100) if total_trip_value else 0

	return [
		{"label": _("Total Trips"), "value": total_trips, "indicator": "blue", "icon": "road"},
		{"label": _("Total Distance (km)"), "value": f"{flt(row.get('total_distance', 0)):,.0f}", "indicator": "green", "icon": "tachometer"},
		{"label": _("Total Trip Value"), "value": f"SAR {total_trip_value:,.2f}", "indicator": "blue", "icon": "map-marker"},
		{"label": _("Net Revenue"), "value": f"SAR {total_net:,.2f}", "indicator": "purple", "icon": "money"},
		{"label": _("Total VAT"), "value": f"SAR {total_vat:,.2f}", "indicator": "orange", "icon": "percent"},
		{"label": _("Grand Total"), "value": f"SAR {total_grand:,.2f}", "indicator": "red", "icon": "calculator"},
		{"label": _("Avg / Trip"), "value": f"SAR {avg_per_trip:,.2f}", "indicator": "cyan", "icon": "bar-chart"},
		{"label": _("VAT % of Trip Value"), "value": f"{vat_of_trip_pct:.1f}%", "indicator": "yellow", "icon": "pie-chart"},
	]


def _get_chart_data(filters, period, dimension, metric):
	"""Build chart based on dimension and metric selections."""
	if dimension == "driver":
		return _build_dimension_chart(filters, "driver", metric, limit=12)
	elif dimension == "route":
		return _build_dimension_chart(filters, "route", metric, limit=10)
	else:
		if period == "daily":
			return _build_time_chart(filters, "daily", metric)
		elif period == "weekly":
			return _build_time_chart(filters, "weekly", metric)
		else:
			return _build_dimension_chart(filters, "driver", metric, limit=10)


def _build_dimension_chart(filters, dim, metric, limit=10):
	TI = DocType("Trip Invoice")
	T = DocType("Trip")

	metric_col, metric_label = _get_metric_column(metric)

	if dim == "driver":
		group_col = T.driver
		label_fn = lambda x: x or _("Unassigned")
	elif dim == "route":
		group_col = T.trip_route
		label_fn = lambda x: x or _("No Route")
	else:
		group_col = T.driver
		label_fn = lambda x: x or _("Unassigned")

	q = (
		frappe.qb.from_(TI)
		.left_join(T).on(TI.trip == T.name)
		.select(
			group_col.as_("dim_key"),
			Sum(metric_col).as_("metric_val"),
			Count(TI.name).as_("trip_count"),
		)
		.where(TI.docstatus.lt(2))
		.where(TI.invoice_date >= filters["start_date"])
		.where(TI.invoice_date <= filters["end_date"])
		.groupby(group_col)
		.orderby(Sum(metric_col), order=frappe.qb.desc)
		.limit(limit)
	)
	if filters["driver"]:
		q = q.where(T.driver == filters["driver"])

	rows = q.run(as_dict=True)

	return {
		"title": _("{} by {}").format(metric_label, dim.title()),
		"labels": [label_fn(r["dim_key"]) for r in rows],
		"datasets": [
			{"name": metric_label, "chartType": "bar", "values": [flt(r["metric_val"]) for r in rows]},
			{"name": _("Trips"), "chartType": "line", "values": [r["trip_count"] or 0 for r in rows]},
		],
	}


def _build_time_chart(filters, period, metric):
	TI = DocType("Trip Invoice")
	T = DocType("Trip")

	metric_col, metric_label = _get_metric_column(metric)

	q = (
		frappe.qb.from_(TI)
		.left_join(T).on(TI.trip == T.name)
		.select(
			TI.invoice_date.as_("date"),
			Sum(metric_col).as_("metric_val"),
			Count(TI.name).as_("trip_count"),
		)
		.where(TI.docstatus.lt(2))
		.where(TI.invoice_date >= filters["start_date"])
		.where(TI.invoice_date <= filters["end_date"])
		.groupby(TI.invoice_date)
		.orderby(TI.invoice_date)
	)
	if filters["driver"]:
		q = q.where(T.driver == filters["driver"])

	rows = q.run(as_dict=True)

	if period == "weekly":
		buckets = {}
		for r in rows:
			d = getdate(r["date"])
			wk_start = get_first_day(d)
			key = wk_start.strftime("%Y-%m-%d")
			if key not in buckets:
				buckets[key] = {"val": 0, "count": 0, "end": d}
			buckets[key]["val"] += flt(r["metric_val"])
			buckets[key]["count"] += r["trip_count"] or 0
			if d > buckets[key]["end"]:
				buckets[key]["end"] = d

		labels = [f"Week {getdate(k).strftime('%d %b')}" for k in sorted(buckets)]
		vals = [buckets[k]["val"] for k in sorted(buckets)]
		counts = [buckets[k]["count"] for k in sorted(buckets)]
	elif period == "daily":
		labels = [getdate(r["date"]).strftime("%d %b") for r in rows]
		vals = [flt(r["metric_val"]) for r in rows]
		counts = [r["trip_count"] or 0 for r in rows]
	else:
		labels = [getdate(r["date"]).strftime("%d %b") for r in rows]
		vals = [flt(r["metric_val"]) for r in rows]
		counts = [r["trip_count"] or 0 for r in rows]

	return {
		"title": _("Daily {} Trend").format(metric_label) if period == "daily" else _("Weekly {} Trend").format(metric_label),
		"labels": labels,
		"datasets": [
			{"name": metric_label, "chartType": "bar", "values": vals},
			{"name": _("Trips"), "chartType": "line", "values": counts},
		],
	}


def _get_metric_column(metric):
	mapping = {
		"vat": ("vat_amount", _("VAT")),
		"trip_value": ("trip_value", _("Trip Value")),
		"net": ("net_total", _("Net Revenue")),
		"grand_total": ("grand_total", _("Grand Total")),
		"trip_count": ("name", _("Trip Count")),
		"distance": ("distance", _("Distance")),
	}
	col_name, label = mapping.get(metric, ("vat_amount", _("VAT")))
	TI = DocType("Trip Invoice")
	T = DocType("Trip")

	col_map = {
		"vat_amount": TI.vat_amount,
		"trip_value": T.trip_value,
		"net_total": TI.net_total,
		"grand_total": TI.grand_total,
		"name": TI.name,
		"distance": T.distance,
	}
	return col_map.get(col_name, TI.vat_amount), label


def _get_pivot_data(filters, period, dimension, metric):
	"""Cross-tab pivot: drivers x time periods showing selected metric with color scale."""
	TI = DocType("Trip Invoice")
	T = DocType("Trip")

	metric_col, metric_label = _get_metric_column(metric)

	q = (
		frappe.qb.from_(TI)
		.left_join(T).on(TI.trip == T.name)
		.select(
			T.driver.as_("driver"),
			TI.invoice_date.as_("date"),
			Sum(metric_col).as_("metric_val"),
		)
		.where(TI.docstatus.lt(2))
		.where(TI.invoice_date >= filters["start_date"])
		.where(TI.invoice_date <= filters["end_date"])
		.groupby(T.driver, TI.invoice_date)
		.orderby(T.driver)
	)
	if filters["driver"]:
		q = q.where(T.driver == filters["driver"])

	rows = q.run(as_dict=True)

	if period == "weekly":
		col_keys = _get_week_keys(filters["start_date"], filters["end_date"])
		get_col_key = lambda d: get_first_day(getdate(d)).strftime("%Y-%m-%d")
		col_labels = [f"W{getdate(k).strftime('%d/%m')}" for k in col_keys]
	elif period == "daily":
		col_keys = _get_day_keys(filters["start_date"], filters["end_date"])
		get_col_key = lambda d: str(getdate(d))
		col_labels = [getdate(k).strftime("%d/%m") for k in col_keys]
	else:
		col_keys = []
		get_col_key = None
		col_labels = []

	if period in ("daily", "weekly"):
		driver_data = {}
		for r in rows:
			drv = r["driver"] or _("Unassigned")
			ck = get_col_key(r["date"])
			if drv not in driver_data:
				driver_data[drv] = {k: 0 for k in col_keys}
			if ck in driver_data[drv]:
				driver_data[drv][ck] += flt(r["metric_val"])

		pivot_rows = []
		all_vals = []
		for drv in sorted(driver_data):
			vals = [driver_data[drv].get(k, 0) for k in col_keys]
			all_vals.extend(vals)
			total = sum(vals)
			pivot_rows.append({
				"label": drv,
				"values": vals,
				"total": flt(total),
			})

		col_totals = []
		for k in col_keys:
			col_totals.append(flt(sum(driver_data[drv].get(k, 0) for drv in driver_data)))

		max_val = max(all_vals) if all_vals else 1

		return {
			"type": "cross_tab",
			"metric": metric_label,
			"column_labels": col_labels,
			"column_keys": col_keys,
			"rows": pivot_rows,
			"column_totals": col_totals,
			"max_value": flt(max_val),
			"grand_total": flt(sum(col_totals)),
		}
	else:
		driver_data = {}
		for r in rows:
			drv = r["driver"] or _("Unassigned")
			driver_data[drv] = driver_data.get(drv, 0) + flt(r["metric_val"])

		pivot_rows = []
		all_vals = list(driver_data.values())
		max_val = max(all_vals) if all_vals else 1

		for drv in sorted(driver_data, key=driver_data.get, reverse=True):
			val = driver_data[drv]
			pivot_rows.append({
				"label": drv,
				"values": [flt(val)],
				"total": flt(val),
				"pct": flt((val / max_val) * 100) if max_val else 0,
			})

		return {
			"type": "ranking",
			"metric": metric_label,
			"column_labels": [metric_label],
			"rows": pivot_rows,
			"max_value": flt(max_val),
			"grand_total": flt(sum(all_vals)),
		}


def _get_week_keys(start_date, end_date):
	keys = []
	cursor = get_first_day(start_date)
	while cursor <= end_date:
		keys.append(cursor.strftime("%Y-%m-%d"))
		cursor = add_to_date(cursor, days=7)
	return keys


def _get_day_keys(start_date, end_date):
	keys = []
	cursor = getdate(start_date)
	while cursor <= end_date:
		keys.append(str(cursor))
		cursor = add_to_date(cursor, days=1)
	return keys


def _get_driver_breakdown(filters):
	TI = DocType("Trip Invoice")
	T = DocType("Trip")

	q = (
		frappe.qb.from_(TI)
		.left_join(T).on(TI.trip == T.name)
		.select(
			T.driver.as_("driver"),
			Count(TI.name).as_("trip_count"),
			Coalesce(Sum(T.distance), 0).as_("total_distance"),
			Coalesce(Sum(T.trip_value), 0).as_("total_trip_value"),
			Coalesce(Sum(TI.net_total), 0).as_("total_net"),
			Coalesce(Sum(TI.vat_amount), 0).as_("total_vat"),
			Coalesce(Sum(TI.grand_total), 0).as_("grand_total"),
		)
		.where(TI.docstatus.lt(2))
		.where(TI.invoice_date >= filters["start_date"])
		.where(TI.invoice_date <= filters["end_date"])
		.groupby(T.driver)
		.orderby(Sum(TI.vat_amount), order=frappe.qb.desc)
	)
	if filters["driver"]:
		q = q.where(T.driver == filters["driver"])

	rows = q.run(as_dict=True)

	result = []
	for r in rows:
		trip_count = r["trip_count"] or 0
		result.append({
			"driver": r["driver"] or _("Unassigned"),
			"trip_count": trip_count,
			"total_distance": flt(r["total_distance"]),
			"total_trip_value": flt(r["total_trip_value"]),
			"total_net": flt(r["total_net"]),
			"total_vat": flt(r["total_vat"]),
			"grand_total": flt(r["grand_total"]),
			"avg_per_trip": flt(r["grand_total"] / trip_count) if trip_count else 0,
			"vat_pct": flt((r["total_vat"] / r["total_trip_value"]) * 100) if flt(r["total_trip_value"]) else 0,
		})
	return result


def _get_route_breakdown(filters):
	TI = DocType("Trip Invoice")
	T = DocType("Trip")

	q = (
		frappe.qb.from_(TI)
		.left_join(T).on(TI.trip == T.name)
		.select(
			T.trip_route.as_("route"),
			Count(TI.name).as_("trip_count"),
			Sum(TI.vat_amount).as_("total_vat"),
			Sum(TI.grand_total).as_("grand_total"),
		)
		.where(TI.docstatus.lt(2))
		.where(TI.invoice_date >= filters["start_date"])
		.where(TI.invoice_date <= filters["end_date"])
		.groupby(T.trip_route)
		.orderby(Sum(TI.vat_amount), order=frappe.qb.desc)
		.limit(10)
	)
	if filters["driver"]:
		q = q.where(T.driver == filters["driver"])

	return q.run(as_dict=True)


def _get_daily_breakdown(filters):
	TI = DocType("Trip Invoice")
	T = DocType("Trip")

	q = (
		frappe.qb.from_(TI)
		.left_join(T).on(TI.trip == T.name)
		.select(
			TI.invoice_date.as_("date"),
			T.driver.as_("driver"),
			Sum(TI.vat_amount).as_("vat"),
			Sum(TI.net_total).as_("net"),
			Sum(TI.grand_total).as_("grand"),
			Sum(T.trip_value).as_("trip_value"),
			Count(TI.name).as_("trip_count"),
		)
		.where(TI.docstatus.lt(2))
		.where(TI.invoice_date >= filters["start_date"])
		.where(TI.invoice_date <= filters["end_date"])
		.groupby(TI.invoice_date, T.driver)
		.orderby(TI.invoice_date)
	)
	if filters["driver"]:
		q = q.where(T.driver == filters["driver"])

	return q.run(as_dict=True)


def _get_weekly_breakdown(filters):
	return _get_daily_breakdown(filters)


def _get_invoice_list(filters):
	TI = DocType("Trip Invoice")
	T = DocType("Trip")

	q = (
		frappe.qb.from_(TI)
		.left_join(T).on(TI.trip == T.name)
		.select(
			TI.name, TI.invoice_date, T.driver,
			T.assigned_vehicle.as_("vehicle"),
			T.trip_value, TI.net_total, TI.vat_amount,
			TI.grand_total, TI.status,
		)
		.where(TI.docstatus.lt(2))
		.where(TI.invoice_date >= filters["start_date"])
		.where(TI.invoice_date <= filters["end_date"])
		.orderby(TI.invoice_date, order=frappe.qb.desc)
		.limit(100)
	)
	if filters["driver"]:
		q = q.where(T.driver == filters["driver"])

	return q.run(as_dict=True)


def _get_drivers_list(start_date, end_date):
	TI = DocType("Trip Invoice")
	T = DocType("Trip")

	q = (
		frappe.qb.from_(TI)
		.left_join(T).on(TI.trip == T.name)
		.select(T.driver)
		.where(TI.docstatus.lt(2))
		.where(TI.invoice_date >= start_date)
		.where(TI.invoice_date <= end_date)
		.where(T.driver.isnotnull())
		.distinct()
		.orderby(T.driver)
	)

	rows = q.run(as_dict=True)
	return [r["driver"] for r in rows if r.get("driver")]
