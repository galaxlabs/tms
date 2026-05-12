# Copyright (c) 2026, Galaxy Labs and contributors
# For license information, please see license.txt

from collections import OrderedDict

import frappe
from frappe.utils import cstr, flt, getdate, today


INVOICE_DOCTYPES = {
	"sales": ("Sales Invoice", "customer"),
	"purchase": ("Purchase Invoice", "supplier"),
}

VAT_PROCESS_STATUS_ORDER = [
	"Needs Review",
	"Reviewed",
	"Invoice Created",
	"Rejected",
	"Draft",
	"Extracted",
	"Cancelled",
]


@frappe.whitelist()
def get_vat_dashboard_data(company=None, from_date=None, to_date=None, document_mode="live"):
	filters = _normalize_filters(company=company, from_date=from_date, to_date=to_date, document_mode=document_mode)
	currency = _get_currency(filters.company)

	sales_summary = _query_invoice_summary("Sales Invoice", filters)
	purchase_summary = _query_invoice_summary("Purchase Invoice", filters)
	sales_month_rows = _query_invoice_month_rows("Sales Invoice", filters)
	purchase_month_rows = _query_invoice_month_rows("Purchase Invoice", filters)
	status_rows = _query_vat_process_status_rows(filters)
	top_customers = _query_top_parties("Sales Invoice", "customer", filters)
	top_suppliers = _query_top_parties("Purchase Invoice", "supplier", filters)

	totals = _build_totals(sales_summary, purchase_summary)
	audit_signal = _build_audit_signal(totals, currency)
	status_breakdown = _normalize_status_rows(status_rows)
	vat_trend = _build_month_chart(
		sales_month_rows,
		purchase_month_rows,
		left_key="vat_total",
		right_key="vat_total",
		left_name="VAT Collected",
		right_name="VAT Paid",
	)
	net_trend = _build_month_chart(
		sales_month_rows,
		purchase_month_rows,
		left_key="net_total",
		right_key="net_total",
		left_name="Sales Net Total",
		right_name="Purchase Net Total",
	)
	status_distribution = _build_status_distribution_chart(status_breakdown)
	stats = _build_stats(totals, status_breakdown)

	return {
		"filters": {
			"company": filters.company,
			"from_date": str(filters.from_date),
			"to_date": str(filters.to_date),
			"currency": currency,
			"document_mode": filters.document_mode,
		},
		"totals": totals,
		"audit_signal": audit_signal,
		"stats": stats,
		"status_breakdown": status_breakdown,
		"charts": {
			"vat_trend": vat_trend,
			"net_trend": net_trend,
			"status_distribution": status_distribution,
		},
		"top_parties": {
			"customers": top_customers,
			"suppliers": top_suppliers,
		},
		"insights": _build_insights(
			totals, audit_signal, status_breakdown, top_customers, top_suppliers, filters.document_mode
		),
	}


def _normalize_filters(company=None, from_date=None, to_date=None, document_mode="live"):
	default_company = (
		company
		or frappe.defaults.get_user_default("Company")
		or frappe.db.get_single_value("Global Defaults", "default_company")
	)
	start_date = getdate(from_date) if from_date else getdate(f"{getdate(today()).year}-01-01")
	end_date = getdate(to_date) if to_date else getdate(today())
	if start_date > end_date:
		frappe.throw("From Date cannot be after To Date.")
	mode = cstr(document_mode or "live").strip().lower()
	if mode not in {"live", "submitted"}:
		mode = "live"
	return frappe._dict(company=default_company, from_date=start_date, to_date=end_date, document_mode=mode)


def _get_currency(company):
	if company:
		return frappe.db.get_value("Company", company, "default_currency")
	return frappe.db.get_single_value("Global Defaults", "default_currency") or "SAR"


def _query_invoice_summary(doctype, filters):
	table = f"`tab{doctype}`"
	query_filters = frappe._dict(filters)
	query_filters.invoice_doctype = doctype
	conditions, values = _build_invoice_conditions(query_filters)
	query = f"""
		SELECT
			COUNT(name) AS invoice_count,
			COALESCE(SUM(COALESCE(base_net_total, net_total, 0)), 0) AS net_total,
			COALESCE(SUM(COALESCE(base_total_taxes_and_charges, total_taxes_and_charges, 0)), 0) AS vat_total,
			COALESCE(SUM(COALESCE(base_grand_total, grand_total, 0)), 0) AS grand_total
		FROM {table}
		WHERE {' AND '.join(conditions)}
	"""
	return frappe.db.sql(query, values, as_dict=True)[0]


def _query_invoice_month_rows(doctype, filters):
	table = f"`tab{doctype}`"
	query_filters = frappe._dict(filters)
	query_filters.invoice_doctype = doctype
	conditions, values = _build_invoice_conditions(query_filters)
	date_expression = _get_invoice_date_expression(doctype)
	query = f"""
		SELECT
			DATE_FORMAT({date_expression}, '%%Y-%%m') AS month_key,
			DATE_FORMAT({date_expression}, '%%b %%Y') AS month_label,
			COUNT(name) AS invoice_count,
			COALESCE(SUM(COALESCE(base_net_total, net_total, 0)), 0) AS net_total,
			COALESCE(SUM(COALESCE(base_total_taxes_and_charges, total_taxes_and_charges, 0)), 0) AS vat_total
		FROM {table}
		WHERE {' AND '.join(conditions)}
		GROUP BY YEAR({date_expression}), MONTH({date_expression})
		ORDER BY YEAR({date_expression}), MONTH({date_expression})
	"""
	return frappe.db.sql(query, values, as_dict=True)


def _query_top_parties(doctype, party_field, filters, limit=5):
	table = f"`tab{doctype}`"
	query_filters = frappe._dict(filters)
	query_filters.invoice_doctype = doctype
	conditions, values = _build_invoice_conditions(query_filters)
	query = f"""
		SELECT
			{party_field} AS party,
			COUNT(name) AS invoice_count,
			COALESCE(SUM(COALESCE(base_net_total, net_total, 0)), 0) AS net_total,
			COALESCE(SUM(COALESCE(base_total_taxes_and_charges, total_taxes_and_charges, 0)), 0) AS vat_total
		FROM {table}
		WHERE {' AND '.join(conditions)} AND COALESCE({party_field}, '') != ''
		GROUP BY {party_field}
		ORDER BY vat_total DESC, net_total DESC
		LIMIT {int(limit)}
	"""
	return frappe.db.sql(query, values, as_dict=True)


def _query_vat_process_status_rows(filters):
	conditions = ["docstatus < 2", "posting_date >= %(from_date)s", "posting_date <= %(to_date)s"]
	values = {"from_date": filters.from_date, "to_date": filters.to_date}
	if filters.company:
		conditions.append("company = %(company)s")
		values["company"] = filters.company

	query = f"""
		SELECT
			status,
			COUNT(name) AS count,
			COALESCE(SUM(COALESCE(grand_total, 0)), 0) AS grand_total
		FROM `tabVAT Process`
		WHERE {' AND '.join(conditions)}
		GROUP BY status
	"""
	rows = frappe.db.sql(query, values, as_dict=True)
	sort_map = {status: index for index, status in enumerate(VAT_PROCESS_STATUS_ORDER)}
	return sorted(rows, key=lambda row: (sort_map.get(row.status, 999), row.status or ""))


def _build_invoice_conditions(filters):
	date_expression = _get_invoice_date_expression(filters.get("invoice_doctype"))
	conditions = [f"{date_expression} >= %(from_date)s", f"{date_expression} <= %(to_date)s"]
	if cstr(filters.get("document_mode") or "live").lower() == "submitted":
		conditions.insert(0, "docstatus = 1")
	else:
		conditions.insert(0, "docstatus < 2")
	values = {"from_date": filters.from_date, "to_date": filters.to_date}
	if filters.company:
		conditions.append("company = %(company)s")
		values["company"] = filters.company
	return conditions, values


def _get_invoice_date_expression(doctype):
	if cstr(doctype) == "Purchase Invoice":
		return "COALESCE(bill_date, posting_date)"
	return "posting_date"


def _build_totals(sales_summary, purchase_summary):
	vat_collected = flt(sales_summary.get("vat_total"))
	vat_paid = flt(purchase_summary.get("vat_total"))
	sales_invoice_amount = flt(sales_summary.get("grand_total"))
	purchase_invoice_amount = flt(purchase_summary.get("grand_total"))
	sales_invoice_count = int(sales_summary.get("invoice_count") or 0)
	purchase_invoice_count = int(purchase_summary.get("invoice_count") or 0)
	return {
		"sales_net_total": flt(sales_summary.get("net_total")),
		"sales_grand_total": sales_invoice_amount,
		"sales_invoice_amount": sales_invoice_amount,
		"sales_invoice_count": sales_invoice_count,
		"submitted_sales_invoices": sales_invoice_count,
		"purchase_net_total": flt(purchase_summary.get("net_total")),
		"purchase_grand_total": purchase_invoice_amount,
		"purchase_invoice_amount": purchase_invoice_amount,
		"purchase_invoice_count": purchase_invoice_count,
		"submitted_purchase_invoices": purchase_invoice_count,
		"vat_collected": vat_collected,
		"total_collected_vat_amount": vat_collected,
		"vat_paid": vat_paid,
		"total_paid_vat_amount": vat_paid,
		"net_vat_payable": flt(vat_collected - vat_paid),
		"vat_balance_difference": flt(vat_collected - vat_paid),
		"invoice_amount_difference": flt(sales_invoice_amount - purchase_invoice_amount),
		"purchase_minus_sales_difference": flt(purchase_invoice_amount - sales_invoice_amount),
	}


def _build_audit_signal(totals, currency):
	difference = flt(totals.get("net_vat_payable"))
	if difference > 0:
		return {
			"level": "red",
			"title": "Audit Watch Active",
			"message": (
				f"Collected VAT is higher than purchase VAT paid by "
				f"{frappe.format_value(difference, {'fieldtype': 'Currency', 'options': currency})}. "
				"Review missing purchase invoices before filing."
			),
			"difference": difference,
		}
	if difference < 0:
		coverage = abs(difference)
		return {
			"level": "green",
			"title": "Purchase VAT Coverage Healthy",
			"message": (
				f"Purchase VAT paid covers collected VAT by "
				f"{frappe.format_value(coverage, {'fieldtype': 'Currency', 'options': currency})}."
			),
			"difference": difference,
		}
	return {
		"level": "amber",
		"title": "VAT Position Balanced",
		"message": "Collected VAT and purchase VAT paid are currently balanced.",
		"difference": 0,
	}


def _normalize_status_rows(status_rows):
	return [
		{
			"status": row.get("status") or "Unspecified",
			"count": int(row.get("count") or 0),
			"grand_total": flt(row.get("grand_total")),
		}
		for row in status_rows
	]


def _build_month_chart(left_rows, right_rows, left_key, right_key, left_name, right_name):
	index = OrderedDict()
	for row in left_rows or []:
		index.setdefault(row.get("month_key"), {"label": row.get("month_label"), "left": 0, "right": 0})
		index[row.get("month_key")]["left"] = flt(row.get(left_key))
	for row in right_rows or []:
		index.setdefault(row.get("month_key"), {"label": row.get("month_label"), "left": 0, "right": 0})
		index[row.get("month_key")]["right"] = flt(row.get(right_key))

	labels = [row["label"] for row in index.values()]
	return {
		"labels": labels,
		"datasets": [
			{"name": left_name, "values": [row["left"] for row in index.values()]},
			{"name": right_name, "values": [row["right"] for row in index.values()]},
		],
	}


def _build_status_distribution_chart(status_breakdown):
	return {
		"labels": [row["status"] for row in status_breakdown],
		"datasets": [{"name": "VAT Process", "values": [row["count"] for row in status_breakdown]}],
	}


def _build_stats(totals, status_breakdown):
	status_map = {row["status"]: row["count"] for row in status_breakdown}
	vat_collected = flt(totals.get("vat_collected"))
	vat_paid = flt(totals.get("vat_paid"))
	coverage_ratio = 0
	if vat_collected > 0:
		coverage_ratio = flt((vat_paid / vat_collected) * 100, 2)
	elif vat_paid > 0:
		coverage_ratio = 100

	return {
		"vat_coverage_ratio": coverage_ratio,
		"total_vat_processes": sum(status_map.values()),
		"pending_review_count": status_map.get("Needs Review", 0) + status_map.get("Draft", 0) + status_map.get("Extracted", 0),
		"reviewed_count": status_map.get("Reviewed", 0),
		"invoice_created_count": status_map.get("Invoice Created", 0),
		"rejected_count": status_map.get("Rejected", 0),
	}


def _build_insights(totals, audit_signal, status_breakdown, top_customers, top_suppliers, document_mode="live"):
	mode_label = "submitted invoices" if cstr(document_mode).lower() == "submitted" else "live invoices"
	insights = [
		{
			"label": audit_signal.get("title"),
			"value": audit_signal.get("message"),
			"tone": audit_signal.get("level"),
		}
	]

	if status_breakdown:
		busiest_status = max(status_breakdown, key=lambda row: row.get("count") or 0)
		insights.append(
			{
				"label": "Largest VAT Process Queue",
				"value": f"{busiest_status['status']}: {busiest_status['count']} records",
				"tone": "neutral",
			}
		)

	if top_customers:
		customer = top_customers[0]
		insights.append(
			{
				"label": "Top Customer VAT Driver",
				"value": f"{customer['party']} with VAT {flt(customer['vat_total'])}",
				"tone": "neutral",
			}
		)

	if top_suppliers:
		supplier = top_suppliers[0]
		insights.append(
			{
				"label": "Top Supplier VAT Offset",
				"value": f"{supplier['party']} with VAT {flt(supplier['vat_total'])}",
				"tone": "neutral",
			}
		)

	if not totals.get("submitted_sales_invoices") and not totals.get("submitted_purchase_invoices"):
		insights.append(
			{
				"label": "No Invoice Activity",
				"value": f"The selected range has no {mode_label} yet.",
				"tone": "amber",
			}
		)

	return insights
