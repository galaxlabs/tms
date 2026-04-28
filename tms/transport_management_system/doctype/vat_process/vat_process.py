# Copyright (c) 2026, Galaxy Labs and contributors
# For license information, please see license.txt

import base64
import json
import re

import frappe
from frappe import _
from frappe.model.naming import make_autoname
from frappe.model.document import Document
from frappe.utils import cint, cstr, flt, getdate, now_datetime, today
from frappe.utils.file_manager import save_file
from tms.utils.gemini_extract import extract_vat_invoice_with_gemini
from tms.utils.ocr_manager import OCRManager


PROCESS_TYPES = {"Sales": "Sales Invoice", "Purchase": "Purchase Invoice"}
TAX_TEMPLATE_DOCTYPES = {
	"Sales Invoice": "Sales Taxes and Charges Template",
	"Purchase Invoice": "Purchase Taxes and Charges Template",
}
STATUSES = {
	"Draft",
	"Extracted",
	"Needs Review",
	"Reviewed",
	"Invoice Created",
	"Rejected",
	"Cancelled",
}
COMPANY_ARABIC_NAME_FIELDS = ("company_name_arabic", "custom_company_name_arabic")
PARTY_GROUP_DEFAULTS = {"Customer": ("Customer Group", "All Customer Groups"), "Supplier": ("Supplier Group", "All Supplier Groups")}
ALNUM_NORMALIZER = re.compile(r"[\W_]+", re.UNICODE)
NUMERIC_NORMALIZER = re.compile(r"\D+")


def _strip_text(value):
	return cstr(value).strip() if value is not None else ""


def _has_field(doctype, fieldname):
	return bool(frappe.get_meta(doctype).has_field(fieldname))


def _normalize_lookup_text(value):
	return ALNUM_NORMALIZER.sub("", cstr(value or "").strip().lower())


def _normalize_tax_id(value):
	return NUMERIC_NORMALIZER.sub("", cstr(value or ""))


def _get_company_arabic_name(company_doc):
	for fieldname in COMPANY_ARABIC_NAME_FIELDS:
		value = company_doc.get(fieldname)
		if value:
			return value
	return ""


def _coerce_to_list(value):
	if not value:
		return []
	if isinstance(value, list):
		return [item for item in value if item]
	if isinstance(value, tuple):
		return [item for item in value if item]
	if isinstance(value, str):
		value = value.strip()
		if not value:
			return []
		try:
			parsed = json.loads(value)
		except ValueError:
			parsed = None
		if isinstance(parsed, list):
			return [item for item in parsed if item]
		return [item.strip() for item in value.split(",") if item.strip()]
	return [value]


def _extract_base64_payload(content_base64):
	value = cstr(content_base64).strip()
	if not value:
		return b""
	if "," in value:
		value = value.split(",", 1)[1]
	return base64.b64decode(value)


class VATProcess(Document):
	def autoname(self):
		self.name = make_autoname("VAT-PROC-.YYYY.-.#####")

	def validate(self):
		self._clean_text_fields()
		self.apply_scan_defaults()
		self.validate_required_fields()
		self.validate_items()
		self.calculate_totals()
		self.validate_duplicate_source_invoice()
		if not getattr(self.flags, "skip_totals_validation_reset", False):
			self.totals_validated = 0

	def before_submit(self):
		self.apply_scan_defaults()
		self.validate_required_fields()
		self.validate_items()
		self.calculate_totals()

	def calculate_totals(self):
		self.net_total = flt(sum(flt(row.amount) for row in self.items))
		self.vat_amount = flt(sum(flt(row.vat_amount) for row in self.items))
		self.grand_total = flt(self.net_total + self.vat_amount + flt(self.rounding_adjustment))
		self.difference_amount = 0

	def validate_required_fields(self):
		if self.process_type not in PROCESS_TYPES and not self._can_defer_process_type():
			frappe.throw(_("Process Type must be either Sales or Purchase."))
		if self.status and self.status not in STATUSES:
			frappe.throw(_("Status must be one of the configured VAT Process statuses."))
		if self.status == "Rejected" and not _strip_text(self.rejection_reason):
			frappe.throw(_("Rejection Reason is required when status is Rejected."))

	def validate_items(self):
		if not self.items:
			return

		for row in self.items:
			row.qty = flt(row.qty or 1)
			row.rate = flt(row.rate)
			row.vat_rate = flt(row.vat_rate if row.vat_rate is not None else self.vat_rate)
			row.item_group = row.item_group or self._get_default_item_group()
			row.uom = row.uom or "Nos"
			row.is_service_item = 1

			if row.qty <= 0:
				frappe.throw(_("Row #{0}: Qty must be greater than 0.").format(row.idx or 1))
			if row.rate < 0:
				frappe.throw(_("Row #{0}: Rate cannot be negative.").format(row.idx or 1))
			if not row.item_code and not _strip_text(row.item_text or row.item_name):
				frappe.throw(_("Row #{0}: Item Text or Item Code is required.").format(row.idx or 1))

			if row.item_code:
				item_flags = frappe.db.get_value(
					"Item",
					row.item_code,
					["item_name", "is_stock_item", "item_group", "stock_uom"],
					as_dict=True,
				)
				if not item_flags:
					frappe.throw(_("Item {0} does not exist.").format(row.item_code))
				if flt(item_flags.is_stock_item):
					frappe.throw(_("Item {0} is a stock item. VAT Process only allows service items.").format(row.item_code))
				row.item_name = row.item_name or item_flags.item_name
				row.item_group = row.item_group or item_flags.item_group or self._get_default_item_group()
				row.uom = row.uom or item_flags.stock_uom or "Nos"

			row.amount = flt(row.qty * row.rate)
			row.vat_amount = flt(row.amount * row.vat_rate / 100)
			row.total_amount = flt(row.amount + row.vat_amount)

	def validate_duplicate_source_invoice(self):
		external_invoice_no = _strip_text(self.external_invoice_no)
		if not external_invoice_no:
			return

		filters = {
			"name": ["!=", self.name or ""],
			"company": self.company,
			"external_invoice_no": external_invoice_no,
			"docstatus": ["<", 2],
		}
		if self.process_type == "Sales" and self.customer:
			filters["customer"] = self.customer
		elif self.process_type == "Purchase" and self.supplier:
			filters["supplier"] = self.supplier
		else:
			return

		duplicate = frappe.db.exists("VAT Process", filters)
		if duplicate:
			frappe.throw(
				_("VAT Process {0} already exists for invoice reference {1}.").format(
					frappe.bold(duplicate), frappe.bold(external_invoice_no)
				)
			)

	def validate_invoice_creation_allowed(self):
		if self.status != "Reviewed":
			frappe.throw(_("Invoice can only be created when the VAT Process status is Reviewed."))
		if self.created_sales_invoice or self.created_purchase_invoice:
			frappe.throw(_("An ERPNext invoice has already been created from this VAT Process."))
		if self.process_type not in PROCESS_TYPES:
			frappe.throw(_("Process Type is required before creating an invoice."))
		if not self.company:
			frappe.throw(_("Company is required before creating an invoice."))
		if not self.items:
			frappe.throw(_("At least one item row is required before creating an invoice."))
		if self.process_type == "Sales" and not self.customer:
			frappe.throw(_("Customer is required before creating a Sales Invoice."))
		if self.process_type == "Purchase" and not self.supplier:
			frappe.throw(_("Supplier is required before creating a Purchase Invoice."))

	def create_missing_items(self):
		for row in self.items:
			if row.item_code:
				continue

			item_label = _strip_text(row.item_text or row.item_name)
			if not item_label:
				frappe.throw(_("Item Text or Item Name is required to create a missing Item."))

			existing_by_name = frappe.get_all(
				"Item",
				filters={"item_name": item_label},
				fields=["name", "item_name", "is_stock_item"],
				limit=1,
			)
			if existing_by_name:
				existing = existing_by_name[0]
				if flt(existing.is_stock_item):
					frappe.throw(
						_("Existing Item {0} is a stock item and cannot be used in VAT Process.").format(
							existing.name
						)
					)
				row.item_code = existing.name
				row.item_name = existing.item_name
				row.is_service_item = 1
				continue

			item_code = self._build_item_code(item_label)
			existing_item = frappe.db.get_value(
				"Item", item_code, ["name", "item_name", "is_stock_item"], as_dict=True
			)
			if existing_item:
				if flt(existing_item.is_stock_item):
					frappe.throw(
						_("Existing Item {0} is a stock item and cannot be used in VAT Process.").format(
							existing_item.name
						)
					)
				row.item_code = existing_item.name
				row.item_name = existing_item.item_name
				row.is_service_item = 1
				continue

			item_doc = frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": item_code,
					"item_name": item_label,
					"item_group": row.item_group or self._get_default_item_group(),
					"stock_uom": row.uom or "Nos",
					"is_stock_item": 0,
					"include_item_in_manufacturing": 0,
					"is_sales_item": 1,
					"is_purchase_item": 1,
					"disabled": 0,
				}
			)
			self._apply_item_company_defaults(item_doc)
			item_doc.insert(ignore_permissions=True)
			row.item_code = item_doc.name
			row.item_name = item_doc.item_name
			row.item_group = item_doc.item_group
			row.uom = item_doc.stock_uom
			row.is_service_item = 1

	def create_invoice(self):
		self.apply_scan_defaults(allow_party_creation=True)
		self.validate_invoice_creation_allowed()
		self.create_missing_items()
		self.validate_items()
		self.calculate_totals()

		if self.process_type == "Sales":
			invoice = self._build_sales_invoice()
			self.created_invoice_type = "Sales Invoice"
			self.created_sales_invoice = invoice.name
			self.created_purchase_invoice = None
		else:
			invoice = self._build_purchase_invoice()
			self.created_invoice_type = "Purchase Invoice"
			self.created_purchase_invoice = invoice.name
			self.created_sales_invoice = None

		self.invoice_created_on = now_datetime()
		self.invoice_created_by = frappe.session.user
		self.status = "Invoice Created"
		self.flags.skip_totals_validation_reset = True
		self.save(ignore_permissions=True)

		return {"doctype": invoice.doctype, "name": invoice.name}

	def analyze_source_document_with_gemini(self):
		if not self.source_document:
			frappe.throw(_("Please attach a source document before running Gemini analysis."))

		ocr_manager = OCRManager()
		raw_text, ocr_engine = ocr_manager.extract_raw_text(self.source_document)
		extraction = extract_vat_invoice_with_gemini(raw_text, hint=self.notes or "")
		self._apply_gemini_extraction(extraction, raw_text=raw_text, ocr_engine=ocr_engine)
		self.flags.skip_totals_validation_reset = True
		self.save(ignore_permissions=True)

		return {
			"name": self.name,
			"process_type": self.process_type,
			"company": self.company,
			"customer": self.customer,
			"supplier": self.supplier,
			"ocr_engine": ocr_engine,
			"confidence": self.extraction_confidence,
		}

	def _clean_text_fields(self):
		for fieldname in (
			"ocr_reference",
			"external_invoice_no",
			"issuer_name_text",
			"issuer_name_arabic",
			"issuer_vat_no",
			"issuer_cr_no",
			"document_customer_name_text",
			"document_customer_name_arabic",
			"document_customer_vat_no",
			"document_customer_cr_no",
			"company_name_arabic",
			"party_name_text",
			"party_name_arabic",
			"party_vat_no",
			"party_cr_no",
			"notes",
			"rejection_reason",
		):
			self.set(fieldname, _strip_text(self.get(fieldname)))
		if self.extracted_text:
			self.extracted_text = self.extracted_text.strip()
		if self.party_address_text:
			self.party_address_text = self.party_address_text.strip()
		if self.issuer_address_text:
			self.issuer_address_text = self.issuer_address_text.strip()
		if self.document_customer_address_text:
			self.document_customer_address_text = self.document_customer_address_text.strip()

		for row in self.items:
			row.item_text = _strip_text(row.item_text)
			row.item_name = _strip_text(row.item_name)

	def _apply_gemini_extraction(self, extraction, raw_text="", ocr_engine=""):
		extraction = frappe._dict(extraction or {})
		field_map = (
			"issuer_name_text",
			"issuer_name_arabic",
			"issuer_vat_no",
			"issuer_cr_no",
			"issuer_address_text",
			"document_customer_name_text",
			"document_customer_name_arabic",
			"document_customer_vat_no",
			"document_customer_cr_no",
			"document_customer_address_text",
			"external_invoice_no",
			"company_name_arabic",
		)
		for fieldname in field_map:
			if extraction.get(fieldname):
				self.set(fieldname, extraction.get(fieldname))

		if extraction.get("invoice_date"):
			self.invoice_date = getdate(extraction.get("invoice_date"))
		if extraction.get("posting_date"):
			self.posting_date = getdate(extraction.get("posting_date"))
		if extraction.get("vat_rate") is not None:
			self.vat_rate = flt(extraction.get("vat_rate") or self.vat_rate or 15)
		if extraction.get("process_type_hint") in PROCESS_TYPES and not self.process_type:
			self.process_type = extraction.get("process_type_hint")

		if raw_text:
			self.extracted_text = raw_text
		if extraction.get("confidence") is not None:
			self.extraction_confidence = extraction.get("confidence")
		if ocr_engine:
			self.ocr_reference = self.ocr_reference or ocr_engine

		items = extraction.get("items") if isinstance(extraction.get("items"), list) else []
		if items:
			self.set("items", [])
			for item in items:
				item = frappe._dict(item or {})
				self.append(
					"items",
					{
						"item_text": item.get("item_text") or item.get("description") or item.get("item_name"),
						"item_name": item.get("item_name"),
						"qty": flt(item.get("qty") or 1),
						"rate": flt(item.get("rate") or 0),
						"vat_rate": flt(item.get("vat_rate") or extraction.get("vat_rate") or self.vat_rate or 15),
						"uom": item.get("uom") or "Nos",
					},
				)

		self.apply_scan_defaults()
		if self.status in {"Draft", "Extracted"}:
			self.status = "Needs Review" if self.requires_review else "Extracted"

	def apply_scan_defaults(self, allow_party_creation=False):
		self._sync_company_details()
		scan_context = self._has_scan_context()

		issuer_match = self._find_matching_company(
			name_text=self.issuer_name_text,
			name_arabic=self.issuer_name_arabic,
			tax_id=self.issuer_vat_no,
		)
		customer_match = self._find_matching_company(
			name_text=self.document_customer_name_text,
			name_arabic=self.document_customer_name_arabic,
			tax_id=self.document_customer_vat_no,
		)

		inferred_company = None
		inferred_process_type = None
		if customer_match and not issuer_match:
			inferred_company = customer_match
			inferred_process_type = "Purchase"
		elif issuer_match and not customer_match:
			inferred_company = issuer_match
			inferred_process_type = "Sales"

		if inferred_company and (not self.company or scan_context):
			self.company = inferred_company
		if inferred_process_type and (not self.process_type or scan_context):
			self.process_type = inferred_process_type

		self._sync_company_details()
		self._apply_party_details_from_scan()
		self._ensure_party_link_from_scan(allow_create=allow_party_creation)

		if not self.currency and self.company:
			self.currency = frappe.db.get_value("Company", self.company, "default_currency")

	def _has_scan_context(self):
		return bool(
			self.source_document
			or self.ocr_reference
			or self.extracted_text
			or self.issuer_name_text
			or self.issuer_name_arabic
			or self.issuer_vat_no
			or self.document_customer_name_text
			or self.document_customer_name_arabic
			or self.document_customer_vat_no
		)

	def _can_defer_process_type(self):
		return (
			not self.process_type
			and self.status in {"Draft", "Extracted", "Needs Review"}
			and (
				self._has_scan_context()
				or self.source_type in {"Scanner", "Upload", "WhatsApp", "Email", "API"}
			)
		)

	def _sync_company_details(self):
		if not self.company:
			return
		company_doc = frappe.db.get_value(
			"Company",
			self.company,
			["name", "company_name", "tax_id", *[field for field in COMPANY_ARABIC_NAME_FIELDS if _has_field("Company", field)]],
			as_dict=True,
		)
		if not company_doc:
			return
		self.company_name_arabic = self.company_name_arabic or _get_company_arabic_name(company_doc)
		if not self.company_name_arabic:
			self.company_name_arabic = (
				self.document_customer_name_arabic
				if self.process_type == "Purchase"
				else self.issuer_name_arabic if self.process_type == "Sales" else ""
			)

	def _apply_party_details_from_scan(self):
		if self.process_type == "Purchase":
			self.party_name_text = self.party_name_text or self.issuer_name_text
			self.party_name_arabic = self.party_name_arabic or self.issuer_name_arabic
			self.party_vat_no = self.party_vat_no or self.issuer_vat_no
			self.party_cr_no = self.party_cr_no or self.issuer_cr_no
			self.party_address_text = self.party_address_text or self.issuer_address_text
		elif self.process_type == "Sales":
			self.party_name_text = self.party_name_text or self.document_customer_name_text
			self.party_name_arabic = self.party_name_arabic or self.document_customer_name_arabic
			self.party_vat_no = self.party_vat_no or self.document_customer_vat_no
			self.party_cr_no = self.party_cr_no or self.document_customer_cr_no
			self.party_address_text = self.party_address_text or self.document_customer_address_text

	def _find_matching_company(self, name_text=None, name_arabic=None, tax_id=None):
		target_tax = _normalize_tax_id(tax_id)
		normalized_names = {_normalize_lookup_text(name_text), _normalize_lookup_text(name_arabic)}
		normalized_names.discard("")

		fieldnames = ["name", "company_name", "tax_id"]
		for fieldname in COMPANY_ARABIC_NAME_FIELDS:
			if _has_field("Company", fieldname) and fieldname not in fieldnames:
				fieldnames.append(fieldname)

		for company_doc in frappe.get_all("Company", filters={"is_group": 0}, fields=fieldnames):
			company_doc = frappe._dict(company_doc)
			company_tax_id = _normalize_tax_id(company_doc.get("tax_id"))
			if target_tax and company_tax_id and target_tax == company_tax_id:
				return company_doc.name

			company_names = {
				_normalize_lookup_text(company_doc.name),
				_normalize_lookup_text(company_doc.company_name),
				_normalize_lookup_text(_get_company_arabic_name(company_doc)),
			}
			company_names.discard("")
			if normalized_names and normalized_names & company_names:
				return company_doc.name

		return None

	def _ensure_party_link_from_scan(self, allow_create=False):
		if self.process_type == "Purchase":
			self.supplier = self.supplier or self._find_party_link("Supplier")
			if not self.supplier and allow_create and self.create_party_if_missing:
				self.supplier = self._create_party_from_scan("Supplier")
		elif self.process_type == "Sales":
			self.customer = self.customer or self._find_party_link("Customer")
			if not self.customer and allow_create and self.create_party_if_missing:
				self.customer = self._create_party_from_scan("Customer")

	def _find_party_link(self, party_doctype):
		name_field = "supplier_name" if party_doctype == "Supplier" else "customer_name"
		tax_id_value = self.party_vat_no
		normalized_name_candidates = {
			_normalize_lookup_text(self.party_name_text),
			_normalize_lookup_text(self.party_name_arabic),
		}
		normalized_name_candidates.discard("")

		fieldnames = ["name", name_field]
		if _has_field(party_doctype, "tax_id"):
			fieldnames.append("tax_id")

		for party_doc in frappe.get_all(party_doctype, fields=fieldnames):
			party_doc = frappe._dict(party_doc)
			if tax_id_value and _has_field(party_doctype, "tax_id"):
				if _normalize_tax_id(party_doc.get("tax_id")) == _normalize_tax_id(tax_id_value):
					return party_doc.name

			party_names = {
				_normalize_lookup_text(party_doc.name),
				_normalize_lookup_text(party_doc.get(name_field)),
			}
			if normalized_name_candidates & party_names:
				return party_doc.name
		return None

	def _create_party_from_scan(self, party_doctype):
		party_label = self.party_name_text or self.party_name_arabic
		if not party_label:
			return None

		group_doctype, fallback_group = PARTY_GROUP_DEFAULTS[party_doctype]
		group_value = frappe.db.get_value(group_doctype, {}, "name") or fallback_group
		doc_payload = {
			"doctype": party_doctype,
			"supplier_name" if party_doctype == "Supplier" else "customer_name": party_label,
		}
		if party_doctype == "Supplier":
			doc_payload["supplier_group"] = group_value
		else:
			doc_payload["customer_group"] = group_value
			if _has_field(party_doctype, "customer_type"):
				doc_payload["customer_type"] = "Company"
		if _has_field(party_doctype, "tax_id") and self.party_vat_no:
			doc_payload["tax_id"] = self.party_vat_no

		party_doc = frappe.get_doc(doc_payload)
		party_doc.insert(ignore_permissions=True)
		return party_doc.name

	def _get_default_item_group(self):
		return (
			frappe.db.exists("Item Group", "Services")
			or frappe.db.get_single_value("Stock Settings", "item_group")
			or "Services"
		)

	def _build_item_code(self, item_label):
		base = frappe.scrub(item_label).replace("_", "-").upper()[:90] or "VAT-SERVICE-ITEM"
		base_code = f"VAT-SVC-{base}"
		candidate = base_code
		counter = 1
		while frappe.db.exists("Item", candidate):
			is_stock_item = frappe.db.get_value("Item", candidate, "is_stock_item")
			if not flt(is_stock_item):
				return candidate
			candidate = f"{base_code}-{counter}"
			counter += 1
		return candidate

	def _apply_item_company_defaults(self, item_doc):
		if not self.company or not _has_field("Item", "item_defaults"):
			return

		if any(cstr(row.company) == cstr(self.company) for row in (item_doc.get("item_defaults") or [])):
			return

		item_doc.append("item_defaults", {"company": self.company})

	def _build_sales_invoice(self):
		invoice = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"company": self.company,
				"customer": self.customer,
				"posting_date": self.posting_date,
				"due_date": self.posting_date,
				"currency": self.currency,
			}
		)
		self._set_vat_process_reference(invoice)
		manual_tax_template = self._set_default_tax_template(
			invoice, self.customer, "Customer", "sales_taxes_and_charges_template"
		)
		for row in self.items:
			invoice.append(
				"items",
				{
					"item_code": row.item_code,
					"item_name": row.item_name,
					"description": row.item_text or row.item_name,
					"qty": row.qty,
					"uom": row.uom,
					"rate": row.rate,
				},
			)
		if hasattr(invoice, "set_missing_values"):
			invoice.set_missing_values()
		self._apply_manual_template_taxes(invoice, manual_tax_template)
		if hasattr(invoice, "calculate_taxes_and_totals"):
			invoice.calculate_taxes_and_totals()
		invoice.insert(ignore_permissions=True)
		return invoice

	def _build_purchase_invoice(self):
		invoice = frappe.get_doc(
			{
				"doctype": "Purchase Invoice",
				"company": self.company,
				"supplier": self.supplier,
				"posting_date": self.posting_date,
				"bill_no": self.external_invoice_no,
				"bill_date": self.invoice_date or self.posting_date,
				"currency": self.currency,
			}
		)
		self._set_vat_process_reference(invoice)
		manual_tax_template = self._set_default_tax_template(
			invoice, self.supplier, "Supplier", "purchase_taxes_and_charges_template"
		)
		for row in self.items:
			invoice.append(
				"items",
				{
					"item_code": row.item_code,
					"item_name": row.item_name,
					"description": row.item_text or row.item_name,
					"qty": row.qty,
					"uom": row.uom,
					"rate": row.rate,
				},
			)
		if hasattr(invoice, "set_missing_values"):
			invoice.set_missing_values()
		self._apply_manual_template_taxes(invoice, manual_tax_template)
		if hasattr(invoice, "calculate_taxes_and_totals"):
			invoice.calculate_taxes_and_totals()
		invoice.insert(ignore_permissions=True)
		return invoice

	def _set_vat_process_reference(self, invoice):
		for fieldname in ("vat_process", "vat_process_reference"):
			if _has_field(invoice.doctype, fieldname):
				invoice.set(fieldname, self.name)

	def _set_default_tax_template(self, invoice, party_name, party_doctype, party_field):
		if not _has_field(invoice.doctype, "taxes_and_charges") or invoice.get("taxes_and_charges"):
			return None

		tax_template = self._get_tax_template_for_invoice(invoice.doctype, party_name, party_doctype, party_field)
		if not tax_template:
			return None
		template_name, template_doctype = tax_template
		if template_doctype == TAX_TEMPLATE_DOCTYPES.get(invoice.doctype):
			invoice.taxes_and_charges = template_name
			return None
		return tax_template

	def _get_tax_template_for_invoice(self, invoice_doctype, party_name, party_doctype, party_field):
		requested_rate = flt(self.vat_rate or 0)
		invoice_template_doctype = TAX_TEMPLATE_DOCTYPES.get(invoice_doctype)

		if party_name and _has_field(party_doctype, party_field):
			tax_template = frappe.db.get_value(party_doctype, party_name, party_field)
			if tax_template and self._template_matches_vat_rate(invoice_template_doctype, tax_template, requested_rate):
				return tax_template, invoice_template_doctype

		matching_company_template = self._get_company_template_matching_rate(invoice_template_doctype, requested_rate)
		if matching_company_template:
			return matching_company_template, invoice_template_doctype

		if invoice_doctype == "Purchase Invoice":
			fallback_sales_template = self._get_company_template_matching_rate(
				TAX_TEMPLATE_DOCTYPES.get("Sales Invoice"), requested_rate
			)
			if fallback_sales_template:
				return fallback_sales_template, TAX_TEMPLATE_DOCTYPES.get("Sales Invoice")

		fallback_template = self._get_first_company_template(invoice_template_doctype)
		if fallback_template:
			return fallback_template, invoice_template_doctype
		return None

	def _get_first_company_template(self, template_doctype):
		if not template_doctype or not self.company:
			return None
		templates = frappe.get_all(
			template_doctype,
			filters={"company": self.company, "disabled": 0},
			fields=["name", "is_default", "modified"],
			order_by="is_default desc, modified desc",
			limit=1,
		)
		if not templates:
			return None
		first_template = templates[0]
		return first_template.get("name") if isinstance(first_template, dict) else first_template.name

	def _get_company_template_matching_rate(self, template_doctype, requested_rate):
		if not template_doctype or not self.company:
			return None

		templates = frappe.get_all(
			template_doctype,
			filters={"company": self.company, "disabled": 0},
			fields=["name", "is_default", "modified"],
			order_by="is_default desc, modified desc",
		)
		for template in templates:
			template_name = template.get("name") if isinstance(template, dict) else template.name
			if self._template_matches_vat_rate(template_doctype, template_name, requested_rate):
				return template_name
		return None

	def _template_matches_vat_rate(self, template_doctype, template_name, requested_rate):
		if not template_doctype or not template_name:
			return False
		if not requested_rate:
			return True

		template_doc = frappe.get_doc(template_doctype, template_name)
		rates = [flt(row.rate) for row in (template_doc.get("taxes") or []) if flt(row.rate)]
		if not rates:
			return False
		return any(abs(rate - requested_rate) < 0.0001 for rate in rates)

	def _apply_manual_template_taxes(self, invoice, manual_tax_template):
		if not manual_tax_template:
			return

		template_name, template_doctype = manual_tax_template
		template_doc = frappe.get_doc(template_doctype, template_name)
		invoice.set("taxes", [])
		for row in template_doc.get("taxes") or []:
			invoice.append(
				"taxes",
				{
					"charge_type": row.charge_type,
					"account_head": row.account_head,
					"description": row.description,
					"rate": row.rate,
					"cost_center": row.cost_center,
					"included_in_print_rate": row.included_in_print_rate,
					"included_in_paid_amount": getattr(row, "included_in_paid_amount", 0),
				},
			)


@frappe.whitelist()
def create_invoice_from_vat_process(name):
	doc = frappe.get_doc("VAT Process", name)
	return doc.create_invoice()


@frappe.whitelist()
def analyze_vat_process_with_gemini(name):
	doc = frappe.get_doc("VAT Process", name)
	return doc.analyze_source_document_with_gemini()


@frappe.whitelist()
def get_company_users(company):
	"""Return active users linked to the selected company."""
	if not company:
		return []

	user_ids = set()

	if frappe.db.exists("DocType", "User Permission"):
		for user_id in frappe.get_all(
			"User Permission",
			filters={"allow": "Company", "for_value": company},
			pluck="user",
		):
			if user_id:
				user_ids.add(user_id)

	if frappe.db.exists("DocType", "Staff"):
		staff_meta = frappe.get_meta("Staff")
		if staff_meta.has_field("company_name") and staff_meta.has_field("email"):
			staff_filters = {"company_name": company}
			if staff_meta.has_field("enabled"):
				staff_filters["enabled"] = 1
			for user_id in frappe.get_all("Staff", filters=staff_filters, pluck="email"):
				if user_id:
					user_ids.add(user_id)

	if frappe.db.exists("DocType", "Employee"):
		employee_meta = frappe.get_meta("Employee")
		if employee_meta.has_field("company") and employee_meta.has_field("user_id"):
			for user_id in frappe.get_all("Employee", filters={"company": company}, pluck="user_id"):
				if user_id:
					user_ids.add(user_id)

	user_meta = frappe.get_meta("User")
	for fieldname in ("company", "default_company"):
		if user_meta.has_field(fieldname):
			for user_id in frappe.get_all("User", filters={fieldname: company}, pluck="name"):
				if user_id:
					user_ids.add(user_id)

	users = []
	for user in frappe.get_all(
		"User",
		filters={"name": ["in", list(user_ids)] if user_ids else ["in", [""]], "enabled": 1},
		fields=["name", "full_name", "email"],
		order_by="full_name asc",
	):
		users.append(
			{
				"name": user.name,
				"full_name": user.full_name or user.name,
				"email": user.email or user.name,
			}
		)
	return users


@frappe.whitelist()
def create_missing_items_for_vat_process(name):
	doc = frappe.get_doc("VAT Process", name)
	doc.create_missing_items()
	doc.flags.skip_totals_validation_reset = True
	doc.save(ignore_permissions=True)
	return doc.name


@frappe.whitelist()
def sync_created_invoice_for_vat_process(name):
	doc = frappe.get_doc("VAT Process", name)
	invoice_name = doc.created_sales_invoice or doc.created_purchase_invoice
	invoice_doctype = doc.created_invoice_type
	if not invoice_name or not invoice_doctype:
		frappe.throw(_("No ERPNext invoice has been created yet for this VAT Process."))

	invoice = frappe.get_doc(invoice_doctype, invoice_name)
	if invoice.docstatus != 0:
		frappe.throw(_("Only draft invoices can be re-synced from VAT Process."))

	invoice.taxes_and_charges = None
	invoice.set("taxes", [])
	manual_tax_template = doc._set_default_tax_template(
		invoice,
		doc.customer if invoice_doctype == "Sales Invoice" else doc.supplier,
		"Customer" if invoice_doctype == "Sales Invoice" else "Supplier",
		"sales_taxes_and_charges_template" if invoice_doctype == "Sales Invoice" else "purchase_taxes_and_charges_template",
	)
	if hasattr(invoice, "set_missing_values"):
		invoice.set_missing_values()
	doc._apply_manual_template_taxes(invoice, manual_tax_template)
	if hasattr(invoice, "calculate_taxes_and_totals"):
		invoice.calculate_taxes_and_totals()
	invoice.save(ignore_permissions=True)
	return {"doctype": invoice.doctype, "name": invoice.name}


@frappe.whitelist()
def validate_totals_for_vat_process(name):
	doc = frappe.get_doc("VAT Process", name)
	doc.calculate_totals()
	doc.totals_validated = 1
	doc.flags.skip_totals_validation_reset = True
	doc.save(ignore_permissions=True)
	return {
		"net_total": doc.net_total,
		"vat_amount": doc.vat_amount,
		"grand_total": doc.grand_total,
	}


def _attach_file_url_to_vat_process(doc, file_url, file_name=None):
	file_url = _strip_text(file_url)
	if not file_url:
		frappe.throw(_("File URL is required to attach a document to VAT Process."))

	existing_files = frappe.get_all(
		"File",
		filters={"file_url": file_url},
		fields=["name", "file_name", "is_private", "attached_to_doctype", "attached_to_name"],
		order_by="creation desc",
	)

	target = None
	for file_row in existing_files:
		if file_row.attached_to_doctype == doc.doctype and file_row.attached_to_name == doc.name:
			target = frappe.get_doc("File", file_row.name)
			break

	if not target and existing_files:
		seed = existing_files[0]
		if not seed.attached_to_doctype and not seed.attached_to_name:
			target = frappe.get_doc("File", seed.name)
			target.attached_to_doctype = doc.doctype
			target.attached_to_name = doc.name
			target.save(ignore_permissions=True)
		else:
			target = frappe.get_doc(
				{
					"doctype": "File",
					"file_url": file_url,
					"file_name": file_name or seed.file_name or file_url.rsplit("/", 1)[-1],
					"is_private": seed.is_private,
					"attached_to_doctype": doc.doctype,
					"attached_to_name": doc.name,
				}
			)
			target.insert(ignore_permissions=True)

	if not target:
		target = frappe.get_doc(
			{
				"doctype": "File",
				"file_url": file_url,
				"file_name": file_name or file_url.rsplit("/", 1)[-1] or f"{doc.name}-document",
				"is_private": 1,
				"attached_to_doctype": doc.doctype,
				"attached_to_name": doc.name,
			}
		)
		target.insert(ignore_permissions=True)

	return target


def _attach_uploaded_content_to_vat_process(doc, file_name, content_base64, is_private=1):
	if not file_name:
		frappe.throw(_("File Name is required when uploading a VAT Process document."))
	if not content_base64:
		frappe.throw(_("File content is required when uploading a VAT Process document."))
	return save_file(
		file_name,
		_extract_base64_payload(content_base64),
		doc.doctype,
		doc.name,
		is_private=flt(is_private) and 1 or 0,
	)


@frappe.whitelist()
def attach_existing_file_to_vat_process(
	name,
	file_url=None,
	file_urls=None,
	file_name=None,
	content_base64=None,
	is_private=1,
):
	doc = frappe.get_doc("VAT Process", name)
	attachments = []

	if content_base64:
		attachments.append(
			_attach_uploaded_content_to_vat_process(
				doc,
				file_name=file_name or f"{doc.name}-document",
				content_base64=content_base64,
				is_private=is_private,
			)
		)

	for url in _coerce_to_list(file_urls) + _coerce_to_list(file_url):
		attachments.append(_attach_file_url_to_vat_process(doc, url, file_name=file_name))

	if not attachments:
		frappe.throw(_("Please provide a file URL or file content to attach to VAT Process."))

	if not doc.source_document:
		doc.source_document = attachments[0].file_url

	doc.flags.skip_totals_validation_reset = True
	doc.save(ignore_permissions=True)

	return {
		"name": doc.name,
		"file_name": attachments[0].name,
		"file_url": attachments[0].file_url,
		"attachments": [
			{"name": file_doc.name, "file_url": file_doc.file_url, "file_name": file_doc.file_name}
			for file_doc in attachments
		],
	}


@frappe.whitelist()
def create_vat_process_from_upload(
	process_type=None,
	company=None,
	file_url=None,
	file_urls=None,
	file_name=None,
	content_base64=None,
	source_type="Upload",
	posting_date=None,
	status="Draft",
	customer=None,
	supplier=None,
	invoice_date=None,
	external_invoice_no=None,
	currency=None,
	vat_rate=15,
	ocr_reference=None,
	extracted_text=None,
	extraction_confidence=None,
	notes=None,
	issuer_name_text=None,
	issuer_name_arabic=None,
	issuer_vat_no=None,
	issuer_cr_no=None,
	issuer_address_text=None,
	document_customer_name_text=None,
	document_customer_name_arabic=None,
	document_customer_vat_no=None,
	document_customer_cr_no=None,
	document_customer_address_text=None,
	company_name_arabic=None,
	items=None,
	create_party_if_missing=0,
	analyze_with_gemini=0,
):
	item_rows = []
	if items:
		item_rows = json.loads(items) if isinstance(items, str) else items

	doc = frappe.get_doc(
		{
			"doctype": "VAT Process",
			"process_type": process_type,
			"source_type": source_type or "Upload",
			"company": company,
			"posting_date": posting_date or today(),
			"status": status or "Draft",
			"customer": customer,
			"supplier": supplier,
			"invoice_date": invoice_date,
			"external_invoice_no": external_invoice_no,
			"currency": currency,
			"vat_rate": vat_rate,
			"ocr_reference": ocr_reference,
			"extracted_text": extracted_text,
			"extraction_confidence": extraction_confidence,
			"notes": notes,
			"issuer_name_text": issuer_name_text,
			"issuer_name_arabic": issuer_name_arabic,
			"issuer_vat_no": issuer_vat_no,
			"issuer_cr_no": issuer_cr_no,
			"issuer_address_text": issuer_address_text,
			"document_customer_name_text": document_customer_name_text,
			"document_customer_name_arabic": document_customer_name_arabic,
			"document_customer_vat_no": document_customer_vat_no,
			"document_customer_cr_no": document_customer_cr_no,
			"document_customer_address_text": document_customer_address_text,
			"company_name_arabic": company_name_arabic,
			"items": item_rows or [],
			"create_party_if_missing": cint(create_party_if_missing),
		}
	)
	doc.insert(ignore_permissions=True)

	attachment_result = None
	if file_url or file_urls or content_base64:
		attachment_result = attach_existing_file_to_vat_process(
			doc.name,
			file_url=file_url,
			file_urls=file_urls,
			file_name=file_name,
			content_base64=content_base64,
		)

	analysis_result = None
	if cint(analyze_with_gemini) and doc.source_document:
		doc.reload()
		analysis_result = doc.analyze_source_document_with_gemini()

	return {
		"name": doc.name,
		"doctype": doc.doctype,
		"source_document": doc.source_document,
		"attachment": attachment_result,
		"analysis": analysis_result,
	}


@frappe.whitelist()
def get_vat_process_attachments(name):
	attachments = frappe.get_all(
		"File",
		filters={"attached_to_doctype": "VAT Process", "attached_to_name": name},
		fields=["name", "file_name", "file_url", "is_private", "creation"],
		order_by="creation desc",
	)
	return {"count": len(attachments), "attachments": attachments}


@frappe.whitelist()
def create_demo_vat_process_records(company=None):
	company = company or frappe.db.get_single_value("Global Defaults", "default_company")
	if not company:
		frappe.throw(_("Please set a default company before creating demo VAT Process records."))

	customer = _get_or_create_demo_customer()
	supplier = _get_or_create_demo_supplier()

	demo_docs = [
		{
			"process_type": "Sales",
			"source_type": "Manual",
			"status": "Draft",
			"external_invoice_no": "DEMO-SALES-001",
			"customer": customer,
			"notes": "Demo Draft Sales VAT Process",
			"items": [
				{"item_text": "Airport transfer service", "qty": 2, "rate": 150, "vat_rate": 15},
				{"item_text": "Meet and greet service", "qty": 1, "rate": 75, "vat_rate": 15},
			],
		},
		{
			"process_type": "Purchase",
			"source_type": "Upload",
			"status": "Needs Review",
			"external_invoice_no": "DEMO-PURCHASE-001",
			"supplier": supplier,
			"notes": "Demo Needs Review Purchase VAT Process",
			"items": [{"item_text": "Vehicle cleaning service", "qty": 3, "rate": 40, "vat_rate": 15}],
		},
		{
			"process_type": "Sales",
			"source_type": "Scanner",
			"status": "Reviewed",
			"external_invoice_no": "DEMO-SALES-REVIEWED-001",
			"customer": customer,
			"notes": "Demo Reviewed Sales VAT Process",
			"items": [{"item_text": "Corporate shuttle service", "qty": 1, "rate": 500, "vat_rate": 15}],
		},
	]

	created = []
	previous_in_patch = getattr(frappe.flags, "in_patch", False)
	frappe.flags.in_patch = True
	try:
		for index, payload in enumerate(demo_docs, start=1):
			existing_name = frappe.db.get_value(
				"VAT Process",
				{"company": company, "external_invoice_no": payload["external_invoice_no"]},
				"name",
			)
			if existing_name:
				doc = frappe.get_doc("VAT Process", existing_name)
				updated = False
				for fieldname in ("customer", "supplier", "source_type", "notes"):
					if payload.get(fieldname) and not doc.get(fieldname):
						doc.set(fieldname, payload.get(fieldname))
						updated = True
				if updated:
					doc.save(ignore_permissions=True)
			else:
				doc = frappe.get_doc(
					{
						"doctype": "VAT Process",
						"company": company,
						"posting_date": today(),
						"vat_rate": 15,
						**payload,
					}
				)
				doc.insert(ignore_permissions=True)
			attachment_name = f"demo-vat-process-{index}.txt"
			attachment_content = base64.b64encode(
				f"Demo attachment for {doc.name}\n{payload['notes']}\n".encode()
			).decode()
			if not doc.source_document:
				attach_existing_file_to_vat_process(
					doc.name,
					file_name=attachment_name,
					content_base64=attachment_content,
				)
			created.append(doc.name)
	finally:
		frappe.flags.in_patch = previous_in_patch

	return {"count": len(created), "records": created}


def _get_or_create_demo_customer():
	customer = frappe.db.get_value("Customer", {}, "name")
	if customer:
		return customer

	doc = frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": "VAT Process Demo Customer",
			"customer_type": "Company",
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _get_or_create_demo_supplier():
	supplier = frappe.db.get_value("Supplier", {}, "name")
	if supplier:
		return supplier

	supplier_group = frappe.db.get_value("Supplier Group", {}, "name") or "All Supplier Groups"
	doc = frappe.get_doc(
		{
			"doctype": "Supplier",
			"supplier_name": "VAT Process Demo Supplier",
			"supplier_group": supplier_group,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name
