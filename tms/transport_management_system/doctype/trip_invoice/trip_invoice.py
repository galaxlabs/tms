# Copyright (c) 2026, Galaxy Labs and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now_datetime, nowdate


TAX_EXEMPT_CATEGORIES = {"Zero Rated", "Exempt", "Out of Scope"}


def money(value):
	return flt(value, 2)


def calculate_item_amounts(item, vat_mode):
	qty = flt(item.get("qty"))
	rate = flt(item.get("rate"))
	vat_rate = flt(item.get("vat_rate"))
	gross_or_net = qty * rate

	if vat_mode == "Included":
		net = gross_or_net / (1 + (vat_rate / 100)) if vat_rate else gross_or_net
		vat = gross_or_net - net
		total = gross_or_net
	elif vat_mode == "Manual Add VAT":
		net = gross_or_net
		vat = net * vat_rate / 100
		total = net + vat
	else:
		net = gross_or_net
		vat = 0
		total = net

	if item.get("vat_category") in TAX_EXEMPT_CATEGORIES:
		vat = 0
		total = net

	return {
		"amount": money(net),
		"vat_amount": money(vat),
		"total_amount": money(total),
	}


class TripInvoice(Document):
	def validate(self):
		self.set_defaults()
		self.validate_unique_trip()
		self.calculate_totals()

	def set_defaults(self):
		settings = get_trip_invoice_settings()
		self.customer = self.customer or settings.get("default_customer") or "Walking Customer"
		self.company = self.company or settings.get("default_company")
		self.vat_template = self.vat_template or settings.get("default_vat_template")
		self.vat_account = self.vat_account or settings.get("default_vat_account")
		self.vat_rate = flt(self.vat_rate if self.vat_rate is not None else settings.get("default_vat_rate") or 15)
		self.invoice_date = self.invoice_date or nowdate()
		self.status = self.status or "Draft"
		self.resolve_vat_account()

	def validate_unique_trip(self):
		if not self.trip:
			return
		existing = frappe.db.get_value("Trip Invoice", {"trip": self.trip}, "name")
		if existing and existing != self.name:
			frappe.throw(_("Trip Invoice {0} already exists for Trip {1}.").format(existing, self.trip))

	def calculate_totals(self):
		net_total = 0
		vat_amount = 0
		grand_total = 0
		for row in self.get("items") or []:
			row.vat_rate = flt(row.vat_rate if row.vat_rate is not None else self.vat_rate)
			result = calculate_item_amounts(row.as_dict(), self.vat_mode)
			row.amount = result["amount"]
			row.vat_amount = result["vat_amount"]
			row.total_amount = result["total_amount"]
			net_total += row.amount
			vat_amount += row.vat_amount
			grand_total += row.total_amount

		self.net_total = money(net_total)
		self.vat_amount = money(vat_amount)
		self.grand_total = money(grand_total)
		self.rounding_difference = money(self.grand_total - (self.net_total + self.vat_amount))

	def resolve_vat_account(self):
		if self.vat_template or self.vat_account:
			return
		settings = get_trip_invoice_settings()
		if settings.get("default_vat_template"):
			self.vat_template = settings.get("default_vat_template")
			return
		if settings.get("default_vat_account"):
			self.vat_account = settings.get("default_vat_account")
			return
		if not (settings.get("create_missing_vat_account") or self.auto_create_vat_account):
			return
		if not self.company:
			return
		if not set(frappe.get_roles()).intersection({"System Manager", "Accounts Manager", "VAT Manager"}):
			frappe.throw(_("Only System Manager, Accounts Manager, or VAT Manager can auto-create VAT accounts."))
		self.vat_account = get_or_create_vat_account(self.company)


def get_trip_invoice_settings():
	if not frappe.db.exists("DocType", "Trip Invoice Settings"):
		return frappe._dict()
	return frappe.get_single("Trip Invoice Settings").as_dict()


def get_or_create_vat_account(company):
	company_abbr = frappe.db.get_value("Company", company, "abbr")
	account_name = "VAT Output 15%"
	existing = frappe.db.get_value("Account", {"account_name": account_name, "company": company}, "name")
	if existing:
		return existing

	parent_account = frappe.db.get_value(
		"Account",
		{"company": company, "root_type": "Liability", "is_group": 1},
		"name",
	)
	account = frappe.get_doc(
		{
			"doctype": "Account",
			"account_name": account_name,
			"company": company,
			"parent_account": parent_account,
			"account_type": "Tax",
			"is_group": 0,
		}
	)
	account.insert()
	return account.name or f"{account_name} - {company_abbr}"


def get_selected_invoice_passenger(trip):
	selected = [row for row in trip.get("passengers") or [] if flt(row.get("is_invoice_customer"))]
	if len(selected) > 1:
		frappe.throw(_("Only one passenger can be selected as invoice customer."))
	return selected[0] if selected else None


def get_passenger_name(row):
	return row.get("passenger_name") if row else None


def get_passenger_mobile(row):
	if not row:
		return None
	return row.get("mobile_no") or row.get("contact_no")


def make_item_description(trip, passenger_name=None):
	parts = [trip.name]
	if trip.trip_route:
		parts.append(str(trip.trip_route))
	if trip.from_location or trip.to_location:
		parts.append(f"{trip.from_location or ''} to {trip.to_location or ''}".strip())
	if passenger_name:
		parts.append(passenger_name)
	return " | ".join([p for p in parts if p])


def append_auto_trip_item(invoice, trip, settings):
	billing_mode = trip.billing_mode or "Route Amount"
	description = make_item_description(trip, invoice.invoice_passenger_name)
	common = {
		"source_type": "Trip Route",
		"trip": trip.name,
		"route": trip.trip_route,
		"description": description,
		"vat_rate": invoice.vat_rate,
		"income_account": settings.get("default_income_account"),
		"cost_center": settings.get("default_cost_center"),
	}
	if billing_mode == "Route Amount":
		invoice.append(
			"items",
			{
				**common,
				"item_code": settings.get("default_route_item"),
				"qty": 1,
				"uom": settings.get("default_uom_route"),
				"rate": flt(trip.trip_value),
			},
		)
	elif billing_mode == "KM Based":
		if flt(trip.distance) <= 0:
			frappe.throw(_("Distance is required for KM Based billing."))
		invoice.append(
			"items",
			{
				**common,
				"item_code": settings.get("default_km_item"),
				"qty": flt(trip.distance),
				"uom": settings.get("default_uom_km"),
				"rate": flt(trip.trip_value) / flt(trip.distance),
			},
		)


@frappe.whitelist()
def create_trip_invoice_from_trip(trip_name):
	trip = frappe.get_doc("Trip", trip_name)
	existing = frappe.db.get_value("Trip Invoice", {"trip": trip.name}, "name")
	if existing:
		frappe.throw(_("Trip Invoice already exists: {0}").format(existing))

	settings = get_trip_invoice_settings()
	selected_passenger = get_selected_invoice_passenger(trip)
	passenger_name = get_passenger_name(selected_passenger) or trip.get("invoice_passenger_name")
	passenger_mobile = get_passenger_mobile(selected_passenger) or trip.get("invoice_passenger_mobile")
	customer = (
		(selected_passenger.get("customer") if selected_passenger else None)
		or trip.get("customer")
		or settings.get("default_customer")
		or "Walking Customer"
	)

	invoice = frappe.new_doc("Trip Invoice")
	invoice.company = trip.get("company") or settings.get("default_company")
	invoice.trip = trip.name
	invoice.customer = customer
	invoice.invoice_passenger_name = passenger_name
	invoice.invoice_passenger_mobile = passenger_mobile
	invoice.trip_route = trip.trip_route
	invoice.from_location = trip.from_location
	invoice.to_location = trip.to_location
	invoice.distance = flt(trip.distance)
	invoice.trip_value = flt(trip.trip_value)
	invoice.billing_mode = trip.get("billing_mode") or "Route Amount"
	invoice.vat_mode = trip.get("vat_mode") or "Included"
	invoice.vat_rate = flt(trip.get("vat_rate") or settings.get("default_vat_rate") or 15)
	invoice.vat_template = settings.get("default_vat_template")
	invoice.vat_account = settings.get("default_vat_account")
	invoice.tax_category = trip.get("tax_category")
	invoice.invoice_date = nowdate()
	invoice.status = "Draft"

	append_auto_trip_item(invoice, trip, settings)
	invoice.insert()

	trip.db_set("trip_invoice_created", 1)
	trip.db_set("trip_invoice", invoice.name)

	return {
		"trip": trip.name,
		"trip_invoice": invoice.name,
		"trip_invoice_created": 1,
		"status": invoice.status,
		"kashf_ready": invoice.kashf_ready,
		"can_print": invoice.kashf_ready,
	}


@frappe.whitelist()
def mark_trip_invoice_ready(trip_invoice):
	doc = frappe.get_doc("Trip Invoice", trip_invoice)
	if not doc.get("items"):
		frappe.throw(_("At least one item is required before marking Ready."))
	doc.calculate_totals()
	if flt(doc.grand_total) <= 0:
		frappe.throw(_("Grand total must be greater than zero before marking Ready."))
	doc.status = "Ready"
	doc.kashf_ready = 1
	doc.save()
	return {"trip_invoice": doc.name, "status": doc.status, "kashf_ready": doc.kashf_ready}


@frappe.whitelist()
def mark_kashf_sent(trip_invoice):
	doc = frappe.get_doc("Trip Invoice", trip_invoice)
	if doc.status not in ("Ready", "Sales Invoice Created"):
		frappe.throw(_("Kashf can be marked sent only when Trip Invoice is Ready or Sales Invoice Created."))
	doc.kashf_sent = 1
	doc.kashf_sent_on = now_datetime()
	doc.save()
	return {"trip_invoice": doc.name, "kashf_sent": doc.kashf_sent, "kashf_sent_on": doc.kashf_sent_on}


@frappe.whitelist()
def create_sales_invoice_from_trip_invoice(name):
	frappe.throw(_("Sales Invoice creation from Trip Invoice is planned for a later phase."))


@frappe.whitelist()
def bulk_create_sales_invoices_from_trip_invoices(names):
	if isinstance(names, str):
		names = json.loads(names)
	frappe.throw(_("Bulk Sales Invoice creation from Trip Invoices is planned for a later phase."))
