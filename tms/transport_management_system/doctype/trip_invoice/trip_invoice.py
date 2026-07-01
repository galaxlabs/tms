# Copyright (c) 2026, Galaxy Labs and contributors
# For license information, please see license.txt

import json
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.naming import make_autoname
from frappe.utils import flt, now_datetime, nowdate, getdate, cint



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
	elif vat_mode in ("Excluded", "Manual VAT"):
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
	def autoname(self):
		self.name = make_autoname("TINV-.YYYY.-.MM.-.####")

	def validate(self):
		self.set_defaults()
		self.validate_unique_scope()
		self.calculate_totals()

	def on_update(self):
		sync_trip_invoice_to_trip(self)

	def set_defaults(self):
		settings = get_trip_invoice_settings()
		self.customer = self.customer or settings.get("default_customer") or "Walking Customer"
		self.company = self.company or settings.get("default_company")
		self.vat_template = self.vat_template or get_default_vat_template(self.company, settings)
		self.vat_account = self.vat_account or get_default_vat_account(self.company, settings)
		self.vat_rate = flt(self.vat_rate if self.vat_rate is not None else settings.get("default_vat_rate") or 15)
		self.invoice_date = self.invoice_date or nowdate()
		self.status = self.status or "Draft"
		self.invoice_scope = self.invoice_scope or "Trip"
		if self.vat_mode == "Manual VAT":
			self.vat_mode = "Excluded"
		self.resolve_vat_account()

	def validate_unique_scope(self):
		if not self.trip:
			return
		filters = {"trip": self.trip, "invoice_scope": self.invoice_scope or "Trip"}
		if self.invoice_scope == "Passenger":
			filters["passenger_row"] = self.passenger_row
		existing = frappe.db.get_value("Trip Invoice", filters, "name")
		if existing and existing != self.name:
			frappe.throw(_("Trip Invoice {0} already exists for this Trip scope.").format(existing))

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
		default_template = get_default_vat_template(self.company, settings)
		if default_template:
			self.vat_template = default_template
			return
		default_account = get_default_vat_account(self.company, settings)
		if default_account:
			self.vat_account = default_account
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


def get_default_vat_template(company=None, settings=None):
	settings = settings or get_trip_invoice_settings()
	if company:
		abbr = frappe.db.get_value("Company", company, "abbr")
		if abbr:
			dynamic_template = f"KSA VAT 15% - {abbr}"
			if frappe.db.exists("Sales Taxes and Charges Template", dynamic_template):
				return dynamic_template
	for template in (settings.get("default_vat_template"), "KSA VAT 15%"):
		if template and frappe.db.exists("Sales Taxes and Charges Template", template):
			return template
	return None


def get_default_vat_account(company=None, settings=None):
	settings = settings or get_trip_invoice_settings()
	if company:
		abbr = frappe.db.get_value("Company", company, "abbr")
		if abbr:
			dynamic_account = f"VAT 15% - {abbr}"
			if frappe.db.exists("Account", dynamic_account):
				return dynamic_account
	fallback = settings.get("default_vat_account") or "VAT 15% - CELTC"
	if fallback and frappe.db.exists("Account", fallback):
		return fallback
	return settings.get("default_vat_account")


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


def get_trip_passengers(trip):
	return [
		row
		for row in trip.get("passengers") or []
		if row.get("passenger_name")
		or row.get("document_number")
		or row.get("contact_no")
		or row.get("id_no")
		or row.get("mobile_no")
	]


def get_uninvoiced_passengers(trip):
	return [row for row in get_trip_passengers(trip) if not cint(row.get("trip_invoice_created"))]


def get_per_passenger_value(trip):
	passenger_count = len(get_trip_passengers(trip))
	if passenger_count <= 0:
		return flt(trip.trip_value)
	return flt(trip.trip_value) / passenger_count


def get_route_label(value, prefer_arabic=True):
	parts = [part.strip() for part in str(value or "").split("|") if part and part.strip()]
	if not parts:
		return ""
	if prefer_arabic and len(parts) > 1:
		return parts[1]
	return parts[0]


def make_item_description(trip, passenger_name=None):
	from_label = get_route_label(trip.from_location, prefer_arabic=True)
	to_label = get_route_label(trip.to_location, prefer_arabic=True)
	if from_label and to_label:
		return f"{from_label}-إلى-{to_label}"
	if trip.trip_route:
		return str(trip.trip_route)
	return _("خدمة نقل")


def sync_trip_invoice_to_trip(invoice):
	if not invoice.trip or (invoice.invoice_scope and invoice.invoice_scope != "Trip"):
		return
	if not frappe.db.exists("Trip", invoice.trip):
		return

	values = {"trip_invoice_created": 1, "trip_invoice": invoice.name}
	frappe.db.set_value("Trip", invoice.trip, values, update_modified=False)


def append_auto_trip_item(invoice, trip, settings, rate_override=None, qty_override=None):
	billing_mode = trip.billing_mode or "Route Amount"
	description = make_item_description(trip, invoice.invoice_passenger_name)
	line_rate = flt(rate_override if rate_override is not None else trip.trip_value)
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
		qty = cint(qty_override or 1) or 1
		rate = line_rate / qty if qty > 0 else line_rate
		invoice.append(
			"items",
			{
				**common,
				"item_code": settings.get("default_route_item"),
				"qty": qty,
				"uom": settings.get("default_uom_route"),
				"rate": rate,
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
				"rate": line_rate / flt(trip.distance),
			},
		)


def make_trip_invoice_doc(trip, settings, passenger=None, invoice_scope="Trip", allocated_count=1, rate_override=None):
	passenger_name = get_passenger_name(passenger) or trip.get("invoice_passenger_name")
	passenger_mobile = get_passenger_mobile(passenger) or trip.get("invoice_passenger_mobile")
	customer = (
		(passenger.get("customer") if passenger else None)
		or trip.get("customer")
		or settings.get("default_customer")
		or "Walking Customer"
	)

	invoice = frappe.new_doc("Trip Invoice")
	invoice.company = trip.get("company") or settings.get("default_company")
	invoice.trip = trip.name
	invoice.invoice_scope = invoice_scope
	invoice.passenger_row = passenger.get("name") if passenger else None
	invoice.allocated_passenger_count = allocated_count
	invoice.customer = customer
	invoice.invoice_passenger_name = passenger_name
	invoice.invoice_passenger_mobile = passenger_mobile
	invoice.trip_route = trip.trip_route
	invoice.from_location = trip.from_location
	invoice.to_location = trip.to_location
	invoice.distance = flt(trip.distance)
	invoice.trip_value = flt(rate_override if rate_override is not None else trip.trip_value)
	invoice.billing_mode = trip.get("billing_mode") or "Route Amount"
	invoice.vat_mode = "Excluded" if trip.get("vat_mode") == "Manual VAT" else (trip.get("vat_mode") or "Included")
	invoice.vat_rate = flt(trip.get("vat_rate") or settings.get("default_vat_rate") or 15)
	invoice.vat_template = get_default_vat_template(invoice.company, settings)
	invoice.vat_account = get_default_vat_account(invoice.company, settings)
	invoice.tax_category = trip.get("tax_category")
	invoice.invoice_date = nowdate()
	invoice.status = "Ready"
	invoice.kashf_ready = 1

	if invoice_scope == "Trip" and passenger is None and allocated_count > 1:
		invoice.invoice_passenger_name = trip.get("invoice_passenger_name") or _("Remaining {0} passengers").format(allocated_count)

	qty_override = allocated_count if invoice_scope == "Trip" and allocated_count > 1 else 1
	append_auto_trip_item(invoice, trip, settings, rate_override=rate_override, qty_override=qty_override)
	return invoice


@frappe.whitelist()
def create_trip_invoice_from_trip(trip_name, invoice_mode="Trip", passenger_rows=None):
	trip = frappe.get_doc("Trip", trip_name)
	settings = get_trip_invoice_settings()
	invoice_mode = invoice_mode or "Trip"
	passengers = get_trip_passengers(trip)

	if invoice_mode == "Passenger":
		if passenger_rows:
			if isinstance(passenger_rows, str):
				passenger_rows = json.loads(passenger_rows)
			passengers = [row for row in passengers if row.name in passenger_rows]
		passengers = [row for row in passengers if not cint(row.get("trip_invoice_created"))]
		if not passengers:
			frappe.throw(_("No uninvoiced passengers found for this Trip."))

		per_passenger_value = get_per_passenger_value(trip)
		created = []
		for passenger in passengers:
			invoice = make_trip_invoice_doc(
				trip,
				settings,
				passenger=passenger,
				invoice_scope="Passenger",
				allocated_count=1,
				rate_override=per_passenger_value,
			)
			invoice.insert()
			frappe.db.set_value("Passengers", passenger.name, {"trip_invoice_created": 1}, update_modified=False)
			created.append(invoice)
		trip.db_set("trip_invoice_created", 1)
		if len(created) == 1:
			trip.db_set("trip_invoice", created[0].name)
		return {
			"trip": trip.name,
			"trip_invoice": created[0].name if len(created) == 1 else None,
			"trip_invoices": [doc.name for doc in created],
			"trip_invoice_created": 1,
			"status": "Draft",
			"kashf_ready": 0,
			"can_print": 0,
		}

	if flt(trip.trip_value) <= 0:
		frappe.throw(_("Route value is required before creating Trip Invoice."))

	remaining_passengers = get_uninvoiced_passengers(trip)
	existing_trip_scope = frappe.db.get_value("Trip Invoice", {"trip": trip.name, "invoice_scope": "Trip"}, "name")
	if existing_trip_scope:
		frappe.throw(_("Trip Invoice already exists: {0}").format(existing_trip_scope))

	allocated_count = len(remaining_passengers) or len(passengers) or 1
	rate_override = flt(trip.trip_value)
	if passengers and len(remaining_passengers) != len(passengers):
		rate_override = get_per_passenger_value(trip) * allocated_count

	selected_passenger = get_selected_invoice_passenger(trip)
	invoice = make_trip_invoice_doc(
		trip,
		settings,
		passenger=selected_passenger,
		invoice_scope="Trip",
		allocated_count=allocated_count,
		rate_override=rate_override,
	)
	invoice.insert()

	for passenger in remaining_passengers:
		frappe.db.set_value("Passengers", passenger.name, {"trip_invoice_created": 1}, update_modified=False)

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
	doc.db_set("status", "Ready", update_modified=False)
	doc.db_set("kashf_ready", 1, update_modified=False)
	sync_trip_invoice_to_trip(doc)
	return {"trip_invoice": doc.name, "status": "Ready", "kashf_ready": 1}


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
	doc = frappe.get_doc("Trip Invoice", name)

	if doc.sales_invoice:
		return {
			"trip_invoice": doc.name,
			"sales_invoice": doc.sales_invoice,
		}

	if not doc.get("items"):
		frappe.throw(_("At least one item is required to create Sales Invoice."))

	# Recalculate Trip Invoice totals before creating Sales Invoice
	doc.calculate_totals()

	settings = get_trip_invoice_settings()

	sales_invoice = frappe.new_doc("Sales Invoice")

	# -----------------------------
	# Basic fields
	# -----------------------------
	sales_invoice.company = doc.company
	sales_invoice.customer = doc.customer or settings.get("default_customer") or "Walking Customer"
	if sales_invoice.meta.has_field("customer_name_text"):
		sales_invoice.customer_name_text = doc.get("customer_name_text") or doc.get("invoice_passenger_name") or ""

	# Important:
	# Due Date must not be before Posting Date.
	# So we force due_date = posting_date.
	posting_date = getdate(doc.invoice_date or nowdate())
	due_date = posting_date

	sales_invoice.posting_date = posting_date
	sales_invoice.due_date = due_date
	sales_invoice.set_posting_time = 1

	# Optional custom/payment fields if they exist in your system
	if frappe.get_meta("Sales Invoice").has_field("custom_payment_means"):
		sales_invoice.custom_payment_means = "Cash"

	# -----------------------------
	# Items
	# -----------------------------
	for row in doc.items:
		item_code = row.item_code or settings.get("default_route_item") or settings.get("default_manual_item")

		if not item_code:
			frappe.throw(_("Default item is required before creating Sales Invoice."))

		qty = flt(row.qty or 1)

		if qty <= 0:
			frappe.throw(_("Qty must be greater than zero for item {0}.").format(item_code))

		# Very important:
		# Trip Invoice row.amount is NET amount.
		# If Trip Invoice total is 500 VAT included,
		# row.amount should be around 434.78.
		# Sales Invoice item rate must be NET rate, not gross rate.
		net_rate = flt(row.amount) / qty

		sales_invoice.append(
			"items",
			{
				"item_code": item_code,
				"item_name": row.item_name,
				"description": row.description or row.item_name or item_code,
				"qty": qty,
				"uom": row.uom,
				"rate": money(net_rate),
				"income_account": row.income_account or settings.get("default_income_account"),
				"cost_center": row.cost_center or settings.get("default_cost_center"),
			},
		)

	# -----------------------------
	# VAT / Taxes
	# -----------------------------
	vat_template = doc.vat_template or settings.get("default_vat_template")
	vat_account = doc.vat_account or settings.get("default_vat_account") or get_default_vat_account(doc.company, settings)
	

	if vat_template:
		if vat_template:
			sales_invoice.taxes_and_charges = vat_template

			sales_invoice.set("taxes", [])

			sales_invoice.set_taxes()

		elif vat_account:
			sales_invoice.append(
				"taxes",
				{
					"charge_type": "On Net Total",
					"account_head": vat_account,
					"description": "VAT {0}%".format(flt(doc.vat_rate or 15)),
					"rate": flt(doc.vat_rate or 15),
					"cost_center": settings.get("default_cost_center"),
				},
			)
		else:
			frappe.throw(_("VAT Template or VAT Account is required to create Sales Invoice with VAT."))	

	# -----------------------------
	# Save Sales Invoice as Draft
	# -----------------------------
	sales_invoice.insert(ignore_permissions=True)

	# -----------------------------
	# Update Trip Invoice
	# -----------------------------
	doc.db_set("sales_invoice", sales_invoice.name)
	doc.db_set("status", "Sales Invoice Created")

	return {
		"trip_invoice": doc.name,
		"sales_invoice": sales_invoice.name,
		"net_total": sales_invoice.net_total,
		"vat_amount": sales_invoice.total_taxes_and_charges,
		"grand_total": sales_invoice.grand_total,
	}

@frappe.whitelist()
def bulk_create_sales_invoices_from_trip_invoices(names):
	if isinstance(names, str):
		names = json.loads(names)
	frappe.throw(_("Bulk Sales Invoice creation from Trip Invoices is planned for a later phase."))
