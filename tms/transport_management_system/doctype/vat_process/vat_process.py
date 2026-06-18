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
from tms.utils.party_defaults import (
	get_valid_default_customer_group,
	get_valid_default_supplier_group,
	get_valid_default_territory,
)
from tms.utils.gemini_extract import extract_vat_invoice_with_gemini
from tms.utils.ocr_manager import OCRManager


PROCESS_TYPE_OPTIONS = {
	"Sales Quotation",
	"Sales Order",
	"Proforma Invoice",
	"Sales Invoice",
	"Purchase Order",
	"Purchase Invoice",
	"Project Billing",
	"Service Billing",
}
TARGET_DOCTYPE_MAP = {
	"Sales Quotation": "Quotation",
	"Sales Order": "Sales Order",
	"Proforma Invoice": "Sales Order",
	"Sales Invoice": "Sales Invoice",
	"Purchase Order": "Purchase Order",
	"Purchase Invoice": "Purchase Invoice",
}
LEGACY_PROCESS_TYPE_MAP = {
	"Purchase": "Purchase Invoice",
	"Sales": "Sales Invoice",
	"Quotation": "Sales Quotation",
}
TAX_TEMPLATE_DOCTYPES = {
	"Sales Invoice": "Sales Taxes and Charges Template",
	"Purchase Invoice": "Purchase Taxes and Charges Template",
	"Quotation": "Sales Taxes and Charges Template",
	"Purchase Order": "Purchase Taxes and Charges Template",
}
STATUSES = {
	"Draft",
	"Ready",
	"Document Created",
	"Cancelled",
	"Rejected",
}
LEGACY_STATUS_MAP = {
	"Extracted": "Draft",
	"Needs Review": "Draft",
	"Reviewed": "Ready",
	"Invoice Created": "Document Created",
}
COMPANY_ARABIC_NAME_FIELDS = ("company_name_arabic", "custom_company_name_arabic")
PARTY_GROUP_DEFAULTS = {"Customer": ("Customer Group", "All Customer Groups"), "Supplier": ("Supplier Group", "All Supplier Groups")}
ALNUM_NORMALIZER = re.compile(r"[\W_]+", re.UNICODE)
NUMERIC_NORMALIZER = re.compile(r"\D+")
SUPPORTED_CREATE_PROCESS_TYPES = set(TARGET_DOCTYPE_MAP)
SUPPLIER_PROCESS_TYPES = {"Purchase Invoice", "Purchase Order"}
CUSTOMER_PROCESS_TYPES = {"Sales Quotation", "Sales Order", "Proforma Invoice", "Sales Invoice"}
PURCHASE_GEMINI_PROCESS_TYPES = {"Purchase Invoice"}
CALCULATION_TYPES = {"Qty x Rate", "Lump Sum Amount"}


def _strip_text(value):
	return cstr(value).strip() if value is not None else ""


def _has_field(doctype, fieldname):
	return bool(frappe.get_meta(doctype).has_field(fieldname))


def _has_db_field(doctype, fieldname):
	if fieldname in {"name", "owner", "creation", "modified", "modified_by", "docstatus", "idx", "parent", "parentfield", "parenttype"}:
		return True
	table_name = f"tab{doctype}"
	try:
		return fieldname in (frappe.db.get_table_columns(table_name) or [])
	except Exception:
		try:
			return fieldname in (frappe.db.get_table_columns(doctype) or [])
		except Exception:
			return _has_field(doctype, fieldname)


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


def normalize_process_type(value):
	return LEGACY_PROCESS_TYPE_MAP.get(_strip_text(value), _strip_text(value))


def normalize_status(value):
	return LEGACY_STATUS_MAP.get(_strip_text(value), _strip_text(value))


def get_target_doctype(doc):
	process_type = normalize_process_type(doc.process_type if hasattr(doc, "process_type") else doc.get("process_type"))
	mapping = TARGET_DOCTYPE_MAP

	if process_type not in mapping:
		frappe.throw(_("Unsupported Process Type: {0}").format(process_type or _("Not Set")))

	return mapping[process_type]


def get_source_file_url(doc):
	file_url = (
		doc.get("source_document")
		or doc.get("document_file")
		or doc.get("uploaded_file")
		or doc.get("attachment")
		or doc.get("invoice_file")
	)

	if not file_url:
		frappe.throw(_("Please upload a source document first."))

	return file_url


def get_file_doc_from_url(file_url):
	file_name = frappe.db.get_value("File", {"file_url": file_url}, "name")
	if not file_name:
		frappe.throw(_("Uploaded source file not found in File records."))
	return frappe.get_doc("File", file_name)


class VATProcess(Document):
	def autoname(self):
		self.name = make_autoname("VAT-PROC-.YYYY.-.#####")

	@frappe.whitelist()
	def validate_totals(self):
		self.calculate_totals()
		self.totals_validated = 1
		self.flags.skip_totals_validation_reset = True
		self.save(ignore_permissions=True)
		return {
			"net_total": self.net_total,
			"vat_amount": self.vat_amount,
			"grand_total": self.grand_total,
		}

	@frappe.whitelist()
	def extract_from_source_document(self):
		return self.analyze_source_document_with_gemini()

	@frappe.whitelist()
	def create_or_match_party(self):
		self.apply_scan_defaults(allow_party_creation=bool(self.create_party_if_missing))
		self.flags.skip_totals_validation_reset = True
		self.save(ignore_permissions=True)
		party_doctype, party_field = self._get_party_context()
		return {
			"party_doctype": party_doctype,
			"party_field": party_field,
			"party": self.get(party_field) if party_field else None,
		}

	@frappe.whitelist()
	def create_or_match_items(self):
		self.create_missing_items()
		self.validate_items()
		self.calculate_totals()
		self.flags.skip_totals_validation_reset = True
		self.save(ignore_permissions=True)
		return {"items": len(self.items or []), "net_total": self.net_total}

	@frappe.whitelist()
	def setup_vat_accounts_and_templates(self):
		return _setup_vat_accounts_and_templates_for_doc(self)

	@frappe.whitelist()
	def create_erpnext_document(self):
		return _create_erpnext_document_for_doc(self)

	@frappe.whitelist()
	def update_created_document(self):
		return _update_created_document_for_doc(self)

	@frappe.whitelist()
	def refresh_created_document_link_state(self):
		changed = self._sync_created_document_link_state(persist=True)
		return {
			"changed": changed,
			"created_document_type": self.created_document_type,
			"created_document": self.created_document,
			"status": self.status,
			"review_status": self.review_status,
		}

	def validate(self):
		self._clean_text_fields()
		self._normalize_legacy_values()
		self._sync_created_document_link_state()
		self._populate_terms_from_template()
		self.apply_scan_defaults()
		self.validate_required_fields()
		self._validate_links()
		self.validate_items()
		self.calculate_totals()
		self.validate_duplicate_source_invoice()
		if not getattr(self.flags, "skip_totals_validation_reset", False):
			self.totals_validated = 0

	def before_submit(self):
		self._normalize_legacy_values()
		self._sync_created_document_link_state()
		self._populate_terms_from_template()
		self.apply_scan_defaults()
		self.validate_required_fields()
		self._validate_links()
		self.validate_items()
		self.calculate_totals()

	def _normalize_legacy_values(self):
		self.process_type = normalize_process_type(self.process_type)
		normalized_status = normalize_status(self.status)
		normalized_review_status = normalize_status(self.review_status)
		if not normalized_review_status or (
			normalized_review_status == "Draft" and normalized_status and normalized_status != normalized_review_status
		):
			normalized_review_status = normalized_status or normalized_review_status
		if not normalized_status or (
			normalized_status == "Draft" and normalized_review_status and normalized_review_status != normalized_status
		):
			normalized_status = normalized_review_status or normalized_status
		self.status = normalized_status or "Draft"
		self.review_status = normalized_review_status or self.status
		if self.created_doctype and not self.created_document_type:
			self.created_document_type = self.created_doctype

	def calculate_totals(self):
		self.net_total = flt(sum(flt(row.amount) for row in self.items))
		self.vat_amount = flt(sum(flt(row.vat_amount) for row in self.items))
		self.grand_total = flt(
			self.net_total
			+ self.vat_amount
			+ flt(self.airfreight_charges)
			- flt(self.discount_amount)
			+ flt(self.rounding_adjustment)
		)
		self.difference_amount = 0

	def validate_required_fields(self):
		if not self.company:
			frappe.throw(_("Company is required."))
		if self.process_type not in PROCESS_TYPE_OPTIONS:
			frappe.throw(
				_(
					"Process Type must be one of Sales Quotation, Sales Order, Proforma Invoice, Sales Invoice, Purchase Order, Purchase Invoice, Project Billing, or Service Billing."
				)
			)
		if self.review_status and self.review_status not in STATUSES:
			frappe.throw(_("Status must be one of the configured VAT Process statuses."))
		self.status = self.review_status or self.status or "Draft"

	def validate_items(self):
		if not self.items:
			return

		for row in self.items:
			row.calculation_type = row.calculation_type or "Qty x Rate"
			if row.calculation_type not in CALCULATION_TYPES:
				frappe.throw(_("Row #{0}: Calculation Type must be Qty x Rate or Lump Sum Amount.").format(row.idx or 1))

			row.qty = flt(row.qty)
			if row.qty < 0:
				frappe.throw(_("Row #{0}: Qty cannot be negative.").format(row.idx or 1))
			if not row.qty:
				row.qty = 1

			row.rate = flt(row.rate)
			row.lump_sum_amount = flt(row.lump_sum_amount)
			row.vat_rate = flt(row.vat_rate if row.vat_rate is not None else self.vat_rate)
			row.item_group = row.item_group or self._get_default_item_group()
			row.is_service_item = 1

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
				row.uom = row.uom or item_flags.stock_uom or ""

			self._calculate_item_row(row)

	def validate_duplicate_source_invoice(self):
		external_invoice_no = _strip_text(self.external_invoice_no)
		target_doctype = None
		if self.process_type in SUPPORTED_CREATE_PROCESS_TYPES:
			target_doctype = get_target_doctype(self)
		if not external_invoice_no or target_doctype not in {"Purchase Invoice", "Sales Invoice"}:
			return

		filters = {
			"name": ["!=", self.name or ""],
			"company": self.company,
			"external_invoice_no": external_invoice_no,
			"docstatus": ["<", 2],
		}
		if target_doctype == "Sales Invoice" and self.customer:
			filters["customer"] = self.customer
		elif target_doctype == "Purchase Invoice" and self.supplier:
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
		self._sync_created_document_link_state()
		review_status = self.review_status or self.status
		if review_status not in {"Ready", "Reviewed"}:
			frappe.throw(_("A document can only be created when the VAT Process status is Ready."))
		if self.created_document or self.created_sales_invoice or self.created_purchase_invoice or self.created_quotation or self.created_purchase_order:
			frappe.throw(_("An ERPNext document has already been created from this VAT Process."))
		if self.process_type not in SUPPORTED_CREATE_PROCESS_TYPES:
			frappe.throw(_("Process Type is required before creating a document."))
		if not self.company:
			frappe.throw(_("Company is required before creating a document."))
		if not self.items:
			frappe.throw(_("At least one item row is required before creating a document."))
		target_doctype = get_target_doctype(self)
		if target_doctype in {"Quotation", "Sales Order", "Sales Invoice"} and not self.customer and not (self.party_name_text or self.party_vat_no):
			frappe.throw(_("Customer or party details are required before creating this document."))
		if target_doctype in {"Purchase Order", "Purchase Invoice"} and not self.supplier and not (self.party_name_text or self.party_vat_no):
			frappe.throw(_("Supplier or party details are required before creating this document."))

	def validate_existing_document_update_allowed(self, existing_document):
		review_status = self.review_status or self.status
		if review_status not in {"Ready", "Reviewed", "Document Created"}:
			frappe.throw(_("A created ERPNext document can only be updated when the VAT Process status is Ready or Document Created."))
		if not existing_document:
			frappe.throw(_("No linked ERPNext document was found to update."))
		if cint(getattr(existing_document, "docstatus", 0)) != 0:
			frappe.throw(_("Only draft ERPNext documents can be updated from VAT Process."))
		if self.process_type not in SUPPORTED_CREATE_PROCESS_TYPES:
			frappe.throw(_("Process Type is required before updating a document."))
		if not self.company:
			frappe.throw(_("Company is required before updating a document."))
		if not self.items:
			frappe.throw(_("At least one item row is required before updating the ERPNext document."))
		target_doctype = get_target_doctype(self)
		if cstr(existing_document.doctype) != cstr(target_doctype):
			frappe.throw(_("Linked document type {0} does not match VAT Process target {1}.").format(existing_document.doctype, target_doctype))
		if target_doctype in {"Quotation", "Sales Order", "Sales Invoice"} and not self.customer and not (self.party_name_text or self.party_vat_no):
			frappe.throw(_("Customer or party details are required before updating this document."))
		if target_doctype in {"Purchase Order", "Purchase Invoice"} and not self.supplier and not (self.party_name_text or self.party_vat_no):
			frappe.throw(_("Supplier or party details are required before updating this document."))

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

	def create_document(self):
		return self.create_erpnext_document()

	def create_invoice(self):
		return self.create_document()

	def analyze_source_document_with_gemini(self):
		target_doctype = get_target_doctype(self)
		if target_doctype != "Purchase Invoice":
			frappe.throw(_("Gemini extraction is only available for Purchase Invoice VAT Process records."))

		file_url = get_source_file_url(self)
		file_doc = get_file_doc_from_url(file_url)
		ocr_manager = OCRManager()
		raw_text, ocr_engine = ocr_manager.extract_raw_text(file_doc.file_url)
		extraction = extract_vat_invoice_with_gemini(raw_text, hint=self.notes or "")
		self.source_document = file_doc.file_url
		self.extracted_text = raw_text or self.extracted_text
		self.extraction_json = json.dumps(extraction or {}, ensure_ascii=False, indent=2)
		self.extraction_status = "Failed" if extraction.get("error") else "Extracted"
		self._apply_gemini_extraction(extraction, raw_text=raw_text, ocr_engine=ocr_engine)
		self.flags.skip_totals_validation_reset = True
		self.save(ignore_permissions=True)

		return {
			"name": self.name,
			"process_type": self.process_type,
			"target_doctype": target_doctype,
			"company": self.company,
			"customer": self.customer,
			"supplier": self.supplier,
			"file_url": file_doc.file_url,
			"ocr_engine": ocr_engine,
			"confidence": self.extraction_confidence,
			"extraction_status": self.extraction_status,
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
		for fieldname in ("extracted_text", "party_address_text", "issuer_address_text", "document_customer_address_text"):
			if self.get(fieldname):
				self.set(fieldname, self.get(fieldname).strip())

		for row in self.items:
			row.item_text = _strip_text(row.item_text)
			row.item_name = _strip_text(row.item_name)

	def _populate_terms_from_template(self):
		if not self.tc_name or self.get("terms"):
			return
		self.terms = self._get_terms_template_content() or self.terms

	def _calculate_item_row(self, row):
		if row.calculation_type == "Lump Sum Amount":
			if row.lump_sum_amount < 0:
				frappe.throw(_("Row #{0}: Lump Sum Amount cannot be negative.").format(row.idx or 1))
			row.amount = flt(row.lump_sum_amount)
			row.rate = flt(row.amount / row.qty) if flt(row.qty) else flt(row.amount)
		else:
			if row.rate < 0:
				frappe.throw(_("Row #{0}: Rate cannot be negative.").format(row.idx or 1))
			row.amount = flt(row.qty * row.rate)

		row.vat_amount = flt(row.amount * row.vat_rate / 100)
		row.total_amount = flt(row.amount + row.vat_amount)

	def _apply_gemini_extraction(self, extraction, raw_text="", ocr_engine=""):
		extraction = frappe._dict(extraction or {})
		if extraction.get("external_invoice_no"):
			self.external_invoice_no = extraction.get("external_invoice_no")
		if extraction.get("party_name_text") or extraction.get("issuer_name_text"):
			self.party_name_text = extraction.get("party_name_text") or extraction.get("issuer_name_text")
		if extraction.get("party_vat_no") or extraction.get("issuer_vat_no"):
			self.party_vat_no = extraction.get("party_vat_no") or extraction.get("issuer_vat_no")
		if extraction.get("party_cr_no") or extraction.get("issuer_cr_no"):
			self.party_cr_no = extraction.get("party_cr_no") or extraction.get("issuer_cr_no")
		if extraction.get("party_address_text") or extraction.get("issuer_address_text"):
			self.party_address_text = extraction.get("party_address_text") or extraction.get("issuer_address_text")

		if extraction.get("invoice_date"):
			self.invoice_date = getdate(extraction.get("invoice_date"))
		if extraction.get("posting_date"):
			self.posting_date = getdate(extraction.get("posting_date"))
		if extraction.get("vat_rate") is not None:
			self.vat_rate = flt(extraction.get("vat_rate") or self.vat_rate or 15)

		if raw_text:
			self.extracted_text = raw_text
		if extraction:
			self.extraction_json = json.dumps(dict(extraction), ensure_ascii=False, indent=2)
		if extraction.get("confidence") is not None:
			self.extraction_confidence = extraction.get("confidence")
		if ocr_engine:
			self.ocr_reference = self.ocr_reference or ocr_engine
		if extraction.get("net_total") is not None:
			self.net_total = flt(extraction.get("net_total"))
		if extraction.get("vat_amount") is not None:
			self.vat_amount = flt(extraction.get("vat_amount"))
		if extraction.get("grand_total") is not None:
			self.grand_total = flt(extraction.get("grand_total"))
		if extraction.get("error") and not self.extraction_status:
			self.extraction_status = "Failed"

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
						"calculation_type": item.get("calculation_type") or "Qty x Rate",
						"lump_sum_amount": flt(item.get("lump_sum_amount") or 0),
						"qty": flt(item.get("qty") or 1),
						"rate": flt(item.get("rate") or 0),
						"vat_rate": flt(item.get("vat_rate") or extraction.get("vat_rate") or self.vat_rate or 15),
						"uom": item.get("uom"),
					},
				)

		self.apply_scan_defaults()

	def apply_scan_defaults(self, allow_party_creation=False):
		self._sync_company_details()
		if self.process_type in PURCHASE_GEMINI_PROCESS_TYPES:
			self._apply_party_details_from_scan()
		self.ensure_party_link(allow_create=allow_party_creation)

		if not self.currency and self.company:
			self.currency = frappe.db.get_value("Company", self.company, "default_currency")

	def _has_scan_context(self):
		return bool(
			self.get("source_document")
			or self.get("ocr_reference")
			or self.get("extracted_text")
			or self.get("issuer_name_text")
			or self.get("issuer_name_arabic")
			or self.get("issuer_vat_no")
			or self.get("document_customer_name_text")
			or self.get("document_customer_name_arabic")
			or self.get("document_customer_vat_no")
		)

	def _can_defer_process_type(self):
		return (
			not self.process_type
			and self.status == "Draft"
		)

	def _sync_company_details(self):
		if not self.company:
			return
		company_doc = frappe.db.get_value(
			"Company",
			self.company,
			["name", "company_name", "tax_id", *[field for field in COMPANY_ARABIC_NAME_FIELDS if _has_db_field("Company", field)]],
			as_dict=True,
		)
		if not company_doc:
			return
		self.company_name_arabic = self.company_name_arabic or _get_company_arabic_name(company_doc)
		if not self.company_name_arabic:
			self.company_name_arabic = (
				self.document_customer_name_arabic
				if self.process_type in SUPPLIER_PROCESS_TYPES
				else self.issuer_name_arabic if self.process_type in CUSTOMER_PROCESS_TYPES else ""
			)

	def _apply_party_details_from_scan(self):
		if self.process_type in SUPPLIER_PROCESS_TYPES:
			self.party_name_text = self.party_name_text or self.issuer_name_text
			self.party_name_arabic = self.party_name_arabic or self.issuer_name_arabic
			self.party_vat_no = self.party_vat_no or self.issuer_vat_no
			self.party_cr_no = self.party_cr_no or self.issuer_cr_no
			self.party_address_text = self.party_address_text or self.issuer_address_text
		elif self.process_type in CUSTOMER_PROCESS_TYPES:
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

	def ensure_party_link(self, allow_create=False):
		party_doctype, party_field = self._get_party_context()
		if not party_doctype or not party_field:
			return

		if not self.get(party_field):
			self.set(party_field, self._find_party_link(party_doctype))
		if not self.get(party_field) and allow_create and self.create_party_if_missing:
			self.set(party_field, self._create_party_from_scan(party_doctype))

	def _get_party_context(self):
		if self.process_type in SUPPLIER_PROCESS_TYPES:
			return "Supplier", "supplier"
		if self.process_type in CUSTOMER_PROCESS_TYPES:
			return "Customer", "customer"
		return None, None

	def _validate_links(self):
		if self.project and _has_db_field("Project", "company"):
			project_company = frappe.db.get_value("Project", self.project, "company")
			if project_company and self.company and cstr(project_company) != cstr(self.company):
				frappe.throw(_("Project {0} does not belong to company {1}.").format(self.project, self.company))
		if self.cost_center and _has_db_field("Cost Center", "company"):
			cost_center_company = frappe.db.get_value("Cost Center", self.cost_center, "company")
			if cost_center_company and self.company and cstr(cost_center_company) != cstr(self.company):
				frappe.throw(_("Cost Center {0} does not belong to company {1}.").format(self.cost_center, self.company))

	def _find_party_link(self, party_doctype):
		name_field = "supplier_name" if party_doctype == "Supplier" else "customer_name"
		tax_id_value = self.party_vat_no
		normalized_name_candidates = {
			_normalize_lookup_text(self.party_name_text),
			_normalize_lookup_text(self.party_name_arabic),
		}
		normalized_name_candidates.discard("")

		fieldnames = ["name", name_field]
		for extra_field in ("tax_id", "custom_vat_information", "custom_registration_number"):
			if _has_db_field(party_doctype, extra_field):
				fieldnames.append(extra_field)

		for party_doc in frappe.get_all(party_doctype, fields=fieldnames):
			party_doc = frappe._dict(party_doc)
			if tax_id_value:
				for tax_field in ("tax_id", "custom_vat_information"):
					if tax_field in fieldnames and _normalize_tax_id(party_doc.get(tax_field)) == _normalize_tax_id(tax_id_value):
						return party_doc.name
			if self.party_cr_no and "custom_registration_number" in fieldnames:
				if _normalize_tax_id(party_doc.get("custom_registration_number")) == _normalize_tax_id(self.party_cr_no):
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

		doc_payload = {
			"doctype": party_doctype,
			"supplier_name" if party_doctype == "Supplier" else "customer_name": party_label,
		}
		if party_doctype == "Supplier":
			doc_payload["supplier_group"] = get_valid_default_supplier_group()
		else:
			doc_payload["customer_group"] = get_valid_default_customer_group()
			if _has_field(party_doctype, "customer_type"):
				doc_payload["customer_type"] = "Company"
			if _has_db_field(party_doctype, "territory"):
				doc_payload["territory"] = get_valid_default_territory()
		for vat_field in ("tax_id", "custom_vat_information"):
			if _has_db_field(party_doctype, vat_field) and self.party_vat_no:
				doc_payload[vat_field] = self.party_vat_no
		if _has_db_field(party_doctype, "custom_registration_number") and self.party_cr_no:
			doc_payload["custom_registration_number"] = self.party_cr_no

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

	def create_sales_invoice(self):
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
		self._apply_header_dimensions(invoice)
		self._apply_external_references(invoice)
		manual_tax_template = self._set_default_tax_template(
			invoice, self.customer, "Customer", "sales_taxes_and_charges_template"
		)
		self._append_document_items(invoice)
		if hasattr(invoice, "set_missing_values"):
			invoice.set_missing_values()
		self._apply_manual_template_taxes(invoice, manual_tax_template)
		if hasattr(invoice, "calculate_taxes_and_totals"):
			invoice.calculate_taxes_and_totals()
		self._apply_terms_and_notes(invoice)
		invoice.insert(ignore_permissions=True)
		return invoice

	def create_sales_order(self, is_proforma=False):
		document = frappe.get_doc(
			{
				"doctype": "Sales Order",
				"company": self.company,
				"customer": self.customer,
				"transaction_date": self.posting_date,
				"delivery_date": self.required_by_date or self.posting_date,
				"currency": self.currency,
			}
		)
		self._set_vat_process_reference(document)
		self._apply_header_dimensions(document)
		self._apply_external_references(document)
		if is_proforma and _has_field("Sales Order", "custom_is_proforma"):
			document.custom_is_proforma = 1
		manual_tax_template = self._set_default_tax_template(
			document, self.customer, "Customer", "sales_taxes_and_charges_template"
		)
		self._append_document_items(document)
		if hasattr(document, "set_missing_values"):
			document.set_missing_values()
		self._apply_manual_template_taxes(document, manual_tax_template)
		if hasattr(document, "calculate_taxes_and_totals"):
			document.calculate_taxes_and_totals()
		self._apply_terms_and_notes(document)
		document.insert(ignore_permissions=True)
		return document

	def create_purchase_invoice(self):
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
		self._apply_header_dimensions(invoice)
		self._apply_external_references(invoice)
		for fieldname in ("supplier_invoice_no", "bill_no"):
			if _has_field("Purchase Invoice", fieldname) and self.external_invoice_no:
				invoice.set(fieldname, self.external_invoice_no)
		if _has_field("Purchase Invoice", "bill_date"):
			invoice.bill_date = self.invoice_date or self.posting_date
		manual_tax_template = self._set_default_tax_template(
			invoice, self.supplier, "Supplier", "purchase_taxes_and_charges_template"
		)
		self._append_document_items(invoice)
		if hasattr(invoice, "set_missing_values"):
			invoice.set_missing_values()
		self._apply_manual_template_taxes(invoice, manual_tax_template)
		if hasattr(invoice, "calculate_taxes_and_totals"):
			invoice.calculate_taxes_and_totals()
		self._apply_terms_and_notes(invoice)
		invoice.insert(ignore_permissions=True)
		return invoice

	def create_purchase_order(self):
		if not self.company:
			frappe.throw(_("Company is required before creating a Purchase Order."))
		if not self.supplier:
			frappe.throw(_("Supplier is required before creating a Purchase Order."))
		if not self.posting_date:
			frappe.throw(_("Posting Date is required before creating a Purchase Order."))
		self._populate_terms_from_template()

		document = frappe.get_doc(
			{
				"doctype": "Purchase Order",
				"company": self.company,
				"supplier": self.supplier,
				"transaction_date": self.posting_date,
				"schedule_date": self.required_by_date or self.posting_date,
				"currency": self.currency,
			}
		)
		self._set_vat_process_reference(document)
		self._apply_header_dimensions(document)
		self._apply_external_references(document)
		manual_tax_template = self._set_default_tax_template(
			document, self.supplier, "Supplier", "purchase_taxes_and_charges_template"
		)
		self._apply_vat_process_totals_to_document(document)
		self._append_document_items(document)
		if hasattr(document, "set_missing_values"):
			document.set_missing_values()
		self._apply_manual_template_taxes(document, manual_tax_template)
		if hasattr(document, "calculate_taxes_and_totals"):
			document.calculate_taxes_and_totals()
		self._apply_terms_and_notes(document)
		document.insert(ignore_permissions=True)
		return document

	def create_quotation(self):
		document = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": self.customer,
				"company": self.company,
				"transaction_date": self.posting_date,
				"valid_till": self.valid_till or self.posting_date,
				"order_type": "Sales",
				"currency": self.currency,
			}
		)
		self._set_vat_process_reference(document)
		self._apply_header_dimensions(document)
		self._apply_external_references(document)
		manual_tax_template = self._set_default_tax_template(
			document, self.customer, "Customer", "sales_taxes_and_charges_template"
		)
		self._append_document_items(document)
		if hasattr(document, "set_missing_values"):
			document.set_missing_values()
		self._apply_manual_template_taxes(document, manual_tax_template)
		if hasattr(document, "calculate_taxes_and_totals"):
			document.calculate_taxes_and_totals()
		self._apply_terms_and_notes(document)
		document.insert(ignore_permissions=True)
		return document

	def _append_document_items(self, document):
		for row in self.items:
			payload = {
				"item_code": row.item_code,
				"item_name": row.item_name,
				"description": row.description or row.item_text or row.item_name,
				"qty": row.qty or 1,
				"uom": row.uom or "Nos",
				"rate": row.rate,
				"amount": row.amount,
			}
			project = row.project or self.project
			cost_center = row.cost_center or self.cost_center
			if project and _has_field(document.doctype + " Item", "project"):
				payload["project"] = project
			if cost_center and _has_field(document.doctype + " Item", "cost_center"):
				payload["cost_center"] = cost_center
			if row.income_account and _has_field(document.doctype + " Item", "income_account"):
				payload["income_account"] = row.income_account
			if row.expense_account and _has_field(document.doctype + " Item", "expense_account"):
				payload["expense_account"] = row.expense_account
			if document.doctype == "Purchase Order":
				payload["schedule_date"] = self.required_by_date or self.posting_date
			if document.doctype == "Sales Order" and _has_field("Sales Order Item", "delivery_date"):
				payload["delivery_date"] = self.required_by_date or self.posting_date
			document.append("items", payload)

	def _apply_terms_and_notes(self, document):
		if self.tc_name and _has_field(document.doctype, "tc_name"):
			document.tc_name = self.tc_name
		effective_terms = self._get_effective_terms_text()
		if effective_terms and _has_field(document.doctype, "terms"):
			document.set("terms", effective_terms)
			document.terms = effective_terms
		if self.print_notes:
			for fieldname in ("remarks", "note", "other_charges_calculation"):
				if _has_field(document.doctype, fieldname) and not document.get(fieldname):
					document.set(fieldname, self.print_notes)
					break

	def _apply_header_dimensions(self, document):
		for fieldname in ("project", "cost_center"):
			if self.get(fieldname) and _has_field(document.doctype, fieldname):
				document.set(fieldname, self.get(fieldname))
		if self.site_location and _has_field(document.doctype, "location"):
			document.set("location", self.site_location)

	def _apply_external_references(self, document):
		reference_value = self.external_order_no or self.external_invoice_no
		for fieldname in ("po_no", "customer_reference", "vendor_ref_no", "supplier_reference"):
			if reference_value and _has_field(document.doctype, fieldname) and not document.get(fieldname):
				document.set(fieldname, reference_value)
		for fieldname in ("custom_vendor_ref", "custom_delivery_terms"):
			if _has_field(document.doctype, fieldname) and self.external_order_no and not document.get(fieldname):
				document.set(fieldname, self.external_order_no)

	def _get_effective_terms_text(self):
		if self.terms:
			return self.terms
		if self.tc_name:
			return self._get_terms_template_content()
		return ""

	def _get_terms_template_content(self):
		if not self.tc_name or not frappe.db.exists("Terms and Conditions", self.tc_name):
			return ""
		return frappe.get_doc("Terms and Conditions", self.tc_name).get("terms") or ""

	def _apply_vat_process_totals_to_document(self, document):
		for fieldname in ("discount_amount", "airfreight_charges", "custom_airfreight_charges", "custom_discount_amount"):
			if not _has_field(document.doctype, fieldname):
				continue
			if "discount" in fieldname:
				document.set(fieldname, flt(self.discount_amount))
			else:
				document.set(fieldname, flt(self.airfreight_charges))

	def _get_created_document_reference(self):
		references = []
		if self.created_document_type and self.created_document:
			references.append((self.created_document_type, self.created_document))
		for doctype, fieldname in (
			("Sales Invoice", "created_sales_invoice"),
			("Purchase Invoice", "created_purchase_invoice"),
			("Purchase Order", "created_purchase_order"),
			("Quotation", "created_quotation"),
		):
			value = self.get(fieldname)
			if value:
				references.append((doctype, value))

		seen = set()
		for doctype, name in references:
			key = (cstr(doctype), cstr(name))
			if key in seen or not doctype or not name:
				continue
			seen.add(key)
			return doctype, name
		return None, None

	def _clear_created_document_links(self):
		for fieldname in (
			"created_doctype",
			"created_document_type",
			"created_document",
			"created_invoice_type",
			"created_sales_invoice",
			"created_purchase_invoice",
			"created_purchase_order",
			"created_quotation",
			"invoice_created_on",
			"invoice_created_by",
		):
			self.set(fieldname, None if fieldname in {"invoice_created_on", "invoice_created_by"} else "")

	def _sync_created_document_link_state(self, persist=False):
		created_doctype, created_name = self._get_created_document_reference()
		changed = False

		if not created_doctype or not created_name:
			return False

		if not frappe.db.exists(created_doctype, created_name):
			self._clear_created_document_links()
			if (self.review_status or self.status) == "Document Created":
				self.status = "Ready"
				self.review_status = "Ready"
			changed = True
		else:
			canonical = (
				cstr(self.created_document_type) != cstr(created_doctype)
				or cstr(self.created_document) != cstr(created_name)
				or (created_doctype == "Sales Invoice" and cstr(self.created_sales_invoice) != cstr(created_name))
				or (created_doctype == "Purchase Invoice" and cstr(self.created_purchase_invoice) != cstr(created_name))
				or (created_doctype == "Purchase Order" and cstr(self.created_purchase_order) != cstr(created_name))
				or (created_doctype == "Quotation" and cstr(self.created_quotation) != cstr(created_name))
			)
			if canonical:
				self._set_created_document(frappe._dict(doctype=created_doctype, name=created_name))
				changed = True

		if persist and changed:
			self.flags.skip_totals_validation_reset = True
			self.save(ignore_permissions=True)

		return changed

	def _reset_document_for_sync(self, document):
		if _has_field(document.doctype, "taxes_and_charges"):
			document.taxes_and_charges = None
		if hasattr(document, "set"):
			document.set("items", [])
			document.set("taxes", [])

	def update_sales_invoice(self, invoice):
		invoice.company = self.company
		invoice.customer = self.customer
		invoice.posting_date = self.posting_date
		if _has_field("Sales Invoice", "due_date"):
			invoice.due_date = self.posting_date
		if _has_field("Sales Invoice", "currency") and self.currency:
			invoice.currency = self.currency
		self._set_vat_process_reference(invoice)
		self._apply_header_dimensions(invoice)
		self._apply_external_references(invoice)
		self._reset_document_for_sync(invoice)
		manual_tax_template = self._set_default_tax_template(invoice, self.customer, "Customer", "sales_taxes_and_charges_template")
		self._append_document_items(invoice)
		if hasattr(invoice, "set_missing_values"):
			invoice.set_missing_values()
		self._apply_manual_template_taxes(invoice, manual_tax_template)
		if hasattr(invoice, "calculate_taxes_and_totals"):
			invoice.calculate_taxes_and_totals()
		self._apply_terms_and_notes(invoice)
		invoice.save(ignore_permissions=True)
		return invoice

	def update_sales_order(self, document, is_proforma=False):
		document.company = self.company
		document.customer = self.customer
		document.transaction_date = self.posting_date
		if _has_field("Sales Order", "delivery_date"):
			document.delivery_date = self.required_by_date or self.posting_date
		if _has_field("Sales Order", "currency") and self.currency:
			document.currency = self.currency
		if is_proforma and _has_field("Sales Order", "custom_is_proforma"):
			document.custom_is_proforma = 1
		self._set_vat_process_reference(document)
		self._apply_header_dimensions(document)
		self._apply_external_references(document)
		self._reset_document_for_sync(document)
		manual_tax_template = self._set_default_tax_template(document, self.customer, "Customer", "sales_taxes_and_charges_template")
		self._append_document_items(document)
		if hasattr(document, "set_missing_values"):
			document.set_missing_values()
		self._apply_manual_template_taxes(document, manual_tax_template)
		if hasattr(document, "calculate_taxes_and_totals"):
			document.calculate_taxes_and_totals()
		self._apply_terms_and_notes(document)
		document.save(ignore_permissions=True)
		return document

	def update_purchase_invoice(self, invoice):
		invoice.company = self.company
		invoice.supplier = self.supplier
		invoice.posting_date = self.posting_date
		if _has_field("Purchase Invoice", "currency") and self.currency:
			invoice.currency = self.currency
		for fieldname in ("supplier_invoice_no", "bill_no"):
			if _has_field("Purchase Invoice", fieldname):
				invoice.set(fieldname, self.external_invoice_no or "")
		if _has_field("Purchase Invoice", "bill_date"):
			invoice.bill_date = self.invoice_date or self.posting_date
		self._set_vat_process_reference(invoice)
		self._apply_header_dimensions(invoice)
		self._apply_external_references(invoice)
		self._reset_document_for_sync(invoice)
		manual_tax_template = self._set_default_tax_template(invoice, self.supplier, "Supplier", "purchase_taxes_and_charges_template")
		self._append_document_items(invoice)
		if hasattr(invoice, "set_missing_values"):
			invoice.set_missing_values()
		self._apply_manual_template_taxes(invoice, manual_tax_template)
		if hasattr(invoice, "calculate_taxes_and_totals"):
			invoice.calculate_taxes_and_totals()
		self._apply_terms_and_notes(invoice)
		invoice.save(ignore_permissions=True)
		return invoice

	def update_purchase_order(self, document):
		document.company = self.company
		document.supplier = self.supplier
		document.transaction_date = self.posting_date
		if _has_field("Purchase Order", "schedule_date"):
			document.schedule_date = self.required_by_date or self.posting_date
		if _has_field("Purchase Order", "currency") and self.currency:
			document.currency = self.currency
		self._populate_terms_from_template()
		self._set_vat_process_reference(document)
		self._apply_header_dimensions(document)
		self._apply_external_references(document)
		self._reset_document_for_sync(document)
		manual_tax_template = self._set_default_tax_template(document, self.supplier, "Supplier", "purchase_taxes_and_charges_template")
		self._apply_vat_process_totals_to_document(document)
		self._append_document_items(document)
		if hasattr(document, "set_missing_values"):
			document.set_missing_values()
		self._apply_manual_template_taxes(document, manual_tax_template)
		if hasattr(document, "calculate_taxes_and_totals"):
			document.calculate_taxes_and_totals()
		self._apply_terms_and_notes(document)
		document.save(ignore_permissions=True)
		return document

	def update_quotation(self, document):
		if _has_field("Quotation", "quotation_to"):
			document.quotation_to = "Customer"
		if _has_field("Quotation", "party_name"):
			document.party_name = self.customer
		document.company = self.company
		document.transaction_date = self.posting_date
		if _has_field("Quotation", "valid_till"):
			document.valid_till = self.valid_till or self.posting_date
		if _has_field("Quotation", "order_type"):
			document.order_type = "Sales"
		if _has_field("Quotation", "currency") and self.currency:
			document.currency = self.currency
		self._set_vat_process_reference(document)
		self._apply_header_dimensions(document)
		self._apply_external_references(document)
		self._reset_document_for_sync(document)
		manual_tax_template = self._set_default_tax_template(document, self.customer, "Customer", "sales_taxes_and_charges_template")
		self._append_document_items(document)
		if hasattr(document, "set_missing_values"):
			document.set_missing_values()
		self._apply_manual_template_taxes(document, manual_tax_template)
		if hasattr(document, "calculate_taxes_and_totals"):
			document.calculate_taxes_and_totals()
		self._apply_terms_and_notes(document)
		document.save(ignore_permissions=True)
		return document

	def _validate_party_link_for_document(self):
		party_doctype, party_field = self._get_party_context()
		if not party_field:
			return
		if not self.get(party_field):
			frappe.throw(_("Unable to resolve or create the required {0} for this VAT Process.").format(party_doctype))

	def _set_created_document(self, document):
		self.created_doctype = document.doctype
		self.created_document_type = document.doctype
		self.created_document = document.name
		self.is_proforma = 1 if self.process_type == "Proforma Invoice" else 0
		self.created_invoice_type = document.doctype
		self.created_sales_invoice = document.name if document.doctype == "Sales Invoice" else None
		self.created_purchase_invoice = document.name if document.doctype == "Purchase Invoice" else None
		self.created_purchase_order = document.name if document.doctype == "Purchase Order" else None
		self.created_quotation = document.name if document.doctype == "Quotation" else None

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
		selected_template = None
		if invoice_doctype in {"Quotation", "Sales Order", "Sales Invoice"}:
			selected_template = self.sales_taxes_template
		elif invoice_doctype in {"Purchase Order", "Purchase Invoice"}:
			selected_template = self.purchase_taxes_template
		if selected_template and frappe.db.exists(invoice_template_doctype, selected_template):
			return selected_template, invoice_template_doctype

		if party_name and _has_field(party_doctype, party_field):
			tax_template = frappe.db.get_value(party_doctype, party_name, party_field)
			if tax_template and self._template_matches_vat_rate(invoice_template_doctype, tax_template, requested_rate):
				return tax_template, invoice_template_doctype

		matching_company_template = self._get_company_template_matching_rate(invoice_template_doctype, requested_rate)
		if matching_company_template:
			return matching_company_template, invoice_template_doctype

		if requested_rate:
			created_company_template = self._ensure_company_tax_template(invoice_doctype, requested_rate)
			if created_company_template:
				return created_company_template, invoice_template_doctype

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

	def _ensure_company_tax_template(self, invoice_doctype, requested_rate):
		template_doctype = TAX_TEMPLATE_DOCTYPES.get(invoice_doctype)
		if not template_doctype or not self.company:
			return None

		company_abbr = frappe.db.get_value("Company", self.company, "abbr")
		if not company_abbr:
			return None

		template_name = f"KSA VAT 15% - {company_abbr}"
		existing_template = frappe.db.exists(template_doctype, template_name)
		account_head = self._ensure_company_vat_account(requested_rate)
		cost_center = frappe.db.get_value("Company", self.company, "cost_center")
		tax_category = "VAT" if frappe.db.exists("Tax Category", "VAT") else None

		if existing_template:
			template_doc = frappe.get_doc(template_doctype, template_name)
		else:
			template_doc = frappe.get_doc(
				{
					"doctype": template_doctype,
					"name": template_name,
					"title": "KSA VAT 15%",
					"company": self.company,
					"is_default": 1,
					"disabled": 0,
					"tax_category": tax_category,
				}
			)

		template_doc.title = "KSA VAT 15%"
		template_doc.company = self.company
		if _has_field(template_doctype, "disabled"):
			template_doc.disabled = 0
		if _has_field(template_doctype, "is_default"):
			template_doc.is_default = 1
		if tax_category and _has_field(template_doctype, "tax_category"):
			template_doc.tax_category = tax_category

		template_doc.set(
			"taxes",
			[
				{
					"charge_type": "On Net Total",
					"account_head": account_head,
					"description": f"VAT {requested_rate:g}%",
					"rate": requested_rate,
					"cost_center": cost_center,
				}
			],
		)

		if existing_template:
			template_doc.save(ignore_permissions=True)
		else:
			template_doc.insert(ignore_permissions=True)
		return template_doc.name

	def _ensure_company_vat_account(self, requested_rate):
		if not self.company:
			return None

		company_abbr = frappe.db.get_value("Company", self.company, "abbr")
		if not company_abbr:
			return None

		existing_tax_account = frappe.db.get_value(
			"Account",
			{"company": self.company, "account_type": "Tax", "tax_rate": requested_rate, "is_group": 0},
			"name",
		)
		if existing_tax_account:
			return existing_tax_account

		account_name = f"VAT {requested_rate:g}%"
		account_full_name = f"{account_name} - {company_abbr}"
		if frappe.db.exists("Account", account_full_name):
			return account_full_name

		parent_account = frappe.db.exists("Account", f"2300 - Duties and Taxes - {company_abbr}") or frappe.db.get_value(
			"Account",
			{
				"company": self.company,
				"account_type": "Tax",
				"is_group": 1,
			},
			"name",
		)
		if not parent_account:
			frappe.throw(
				_("Unable to find a parent Duties and Taxes account for company {0}.").format(frappe.bold(self.company))
			)

		account_doc = frappe.get_doc(
			{
				"doctype": "Account",
				"account_name": account_name,
				"company": self.company,
				"parent_account": parent_account,
				"is_group": 0,
				"root_type": "Liability",
				"report_type": "Balance Sheet",
				"account_currency": self.currency or frappe.db.get_value("Company", self.company, "default_currency"),
				"account_type": "Tax",
				"tax_rate": requested_rate,
			}
		)
		account_doc.insert(ignore_permissions=True)
		return account_doc.name

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

	def _get_primary_tax_account(self, template_doctype, template_name):
		if not template_doctype or not template_name or not frappe.db.exists(template_doctype, template_name):
			return None
		template_doc = frappe.get_doc(template_doctype, template_name)
		for row in template_doc.get("taxes") or []:
			if row.account_head:
				return row.account_head
		return None

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


def validate_before_create(doc, target_doctype, existing_document=None):
	if existing_document:
		doc.validate_existing_document_update_allowed(existing_document)
	else:
		doc.validate_invoice_creation_allowed()
	doc.ensure_party_link(allow_create=bool(doc.create_party_if_missing))
	doc._validate_party_link_for_document()
	doc.create_missing_items()
	doc.validate_items()
	doc.calculate_totals()
	doc._validate_links()

	if target_doctype == "Purchase Invoice":
		if not doc.invoice_date:
			frappe.throw(_("Invoice Date is required before creating a Purchase Invoice."))
		if not _strip_text(doc.external_invoice_no):
			frappe.throw(_("External Invoice No is required before creating a Purchase Invoice."))
		duplicate_filters = {"company": doc.company, "supplier": doc.supplier, "docstatus": ["<", 2]}
		if existing_document and getattr(existing_document, "name", None):
			duplicate_filters["name"] = ["!=", existing_document.name]
		for fieldname in ("bill_no", "supplier_invoice_no"):
			if _has_db_field("Purchase Invoice", fieldname):
				duplicate_filters[fieldname] = doc.external_invoice_no
				if frappe.db.exists("Purchase Invoice", duplicate_filters):
					frappe.throw(_("Purchase Invoice already exists for supplier invoice number {0}.").format(doc.external_invoice_no))
				duplicate_filters.pop(fieldname, None)

	if abs(flt(doc.grand_total) - (flt(doc.net_total) + flt(doc.vat_amount) + flt(doc.airfreight_charges) - flt(doc.discount_amount) + flt(doc.rounding_adjustment))) > 0.01:
		frappe.throw(_("VAT Process totals are not in sync. Please validate totals before creating the ERPNext document."))


def _create_erpnext_document_for_doc(doc):
	doc.apply_scan_defaults(allow_party_creation=True)
	target_doctype = get_target_doctype(doc)
	validate_before_create(doc, target_doctype)

	if target_doctype == "Quotation":
		created = doc.create_quotation()
	elif target_doctype == "Sales Order":
		created = doc.create_sales_order(is_proforma=doc.process_type == "Proforma Invoice")
	elif target_doctype == "Sales Invoice":
		created = doc.create_sales_invoice()
	elif target_doctype == "Purchase Order":
		created = doc.create_purchase_order()
	elif target_doctype == "Purchase Invoice":
		created = doc.create_purchase_invoice()
	else:
		frappe.throw(_("Unsupported target doctype: {0}").format(target_doctype))

	doc.invoice_created_on = now_datetime()
	doc.invoice_created_by = frappe.session.user
	doc._set_created_document(created)
	doc.status = "Document Created"
	doc.review_status = "Document Created"
	doc.flags.skip_totals_validation_reset = True
	doc.save(ignore_permissions=True)

	return {"doctype": target_doctype, "name": created.name}





def _update_created_document_for_doc(doc):
	doc.apply_scan_defaults(allow_party_creation=True)
	doc._sync_created_document_link_state()
	created_doctype, created_name = doc._get_created_document_reference()
	if not created_doctype or not created_name:
		frappe.throw(_("No linked ERPNext document exists. Please create a new document first."))

	target_doctype = get_target_doctype(doc)
	if cstr(created_doctype) != cstr(target_doctype):
		frappe.throw(_("Linked document type {0} does not match VAT Process target {1}.").format(created_doctype, target_doctype))

	existing_document = frappe.get_doc(created_doctype, created_name)
	validate_before_create(doc, target_doctype, existing_document=existing_document)

	if target_doctype == "Quotation":
		updated = doc.update_quotation(existing_document)
	elif target_doctype == "Sales Order":
		updated = doc.update_sales_order(existing_document, is_proforma=doc.process_type == "Proforma Invoice")
	elif target_doctype == "Sales Invoice":
		updated = doc.update_sales_invoice(existing_document)
	elif target_doctype == "Purchase Order":
		updated = doc.update_purchase_order(existing_document)
	elif target_doctype == "Purchase Invoice":
		updated = doc.update_purchase_invoice(existing_document)
	else:
		frappe.throw(_("Unsupported target doctype: {0}").format(target_doctype))

	doc._set_created_document(updated)
	doc.status = "Document Created"
	doc.review_status = "Document Created"
	doc.flags.skip_totals_validation_reset = True
	doc.save(ignore_permissions=True)

	return {"doctype": target_doctype, "name": updated.name, "updated": True}

def _setup_vat_accounts_and_templates_for_doc(doc):
	if "VAT Manager" not in frappe.get_roles() and "System Manager" not in frappe.get_roles():
		frappe.throw(_("Only VAT Manager or System Manager can setup VAT accounts and templates."))

	if not doc.company:
		frappe.throw(_("Company is required before VAT setup can run."))

	try:
		existing_before = bool(doc.sales_taxes_template or doc.purchase_taxes_template or doc.sales_vat_account or doc.purchase_vat_account)
		sales_template = doc._get_company_template_matching_rate(TAX_TEMPLATE_DOCTYPES["Sales Invoice"], flt(doc.vat_rate or 15))
		if not sales_template:
			sales_template = doc._ensure_company_tax_template("Sales Invoice", flt(doc.vat_rate or 15))

		purchase_template = doc._get_company_template_matching_rate(TAX_TEMPLATE_DOCTYPES["Purchase Invoice"], flt(doc.vat_rate or 15))
		if not purchase_template:
			purchase_template = doc._ensure_company_tax_template("Purchase Invoice", flt(doc.vat_rate or 15))

		doc.sales_taxes_template = sales_template
		doc.purchase_taxes_template = purchase_template
		doc.sales_vat_account = doc._get_primary_tax_account(TAX_TEMPLATE_DOCTYPES["Sales Invoice"], sales_template) or doc._ensure_company_vat_account(flt(doc.vat_rate or 15))
		doc.purchase_vat_account = doc._get_primary_tax_account(TAX_TEMPLATE_DOCTYPES["Purchase Invoice"], purchase_template) or doc._ensure_company_vat_account(flt(doc.vat_rate or 15))
		doc.setup_status = "Existing" if existing_before else "Created"
		doc.flags.skip_totals_validation_reset = True
		doc.save(ignore_permissions=True)
		return {
			"setup_status": doc.setup_status,
			"sales_vat_account": doc.sales_vat_account,
			"purchase_vat_account": doc.purchase_vat_account,
			"sales_taxes_template": doc.sales_taxes_template,
			"purchase_taxes_template": doc.purchase_taxes_template,
		}
	except Exception:
		doc.setup_status = "Failed"
		doc.flags.skip_totals_validation_reset = True
		doc.save(ignore_permissions=True)
		raise


@frappe.whitelist()
def create_document_from_vat_process(name):
	doc = frappe.get_doc("VAT Process", name)
	return _create_erpnext_document_for_doc(doc)


@frappe.whitelist()
def create_invoice_from_vat_process(name):
	return create_document_from_vat_process(name)


@frappe.whitelist()
def create_erpnext_document(name):
	doc = frappe.get_doc("VAT Process", name)
	doc.check_permission("write")
	return _create_erpnext_document_for_doc(doc)


@frappe.whitelist()
def update_created_document(name):
	doc = frappe.get_doc("VAT Process", name)
	doc.check_permission("write")
	return _update_created_document_for_doc(doc)


@frappe.whitelist()
def refresh_created_document_link_state(name):
	doc = frappe.get_doc("VAT Process", name)
	doc.check_permission("read")
	return doc.refresh_created_document_link_state()


@frappe.whitelist()
def setup_vat_accounts_and_templates(name):
	doc = frappe.get_doc("VAT Process", name)
	doc.check_permission("write")
	return _setup_vat_accounts_and_templates_for_doc(doc)


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
	doc.create_or_match_items()
	return doc.name


@frappe.whitelist()
def create_or_match_party(name):
	doc = frappe.get_doc("VAT Process", name)
	doc.check_permission("write")
	return doc.create_or_match_party()


@frappe.whitelist()
def create_or_match_items(name):
	doc = frappe.get_doc("VAT Process", name)
	doc.check_permission("write")
	return doc.create_or_match_items()


@frappe.whitelist()
def sync_created_invoice_for_vat_process(name):
	doc = frappe.get_doc("VAT Process", name)
	doc.check_permission("write")
	return _update_created_document_for_doc(doc)


@frappe.whitelist()
def validate_totals_for_vat_process(name):
	doc = frappe.get_doc("VAT Process", name)
	return doc.validate_totals()


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
	external_order_no=None,
	document_date=None,
	currency=None,
	vat_rate=15,
	ocr_reference=None,
	extracted_text=None,
	extraction_json=None,
	extraction_status=None,
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
			"process_type": normalize_process_type(process_type),
			"source_type": source_type or "Upload",
			"company": company,
			"posting_date": posting_date or today(),
			"status": status or "Draft",
			"review_status": normalize_status(status or "Draft"),
			"customer": customer,
			"supplier": supplier,
			"invoice_date": invoice_date,
			"external_invoice_no": external_invoice_no,
			"external_order_no": external_order_no,
			"document_date": document_date,
			"currency": currency,
			"vat_rate": vat_rate,
			"ocr_reference": ocr_reference,
			"extracted_text": extracted_text,
			"extraction_json": extraction_json,
			"extraction_status": extraction_status or "Not Extracted",
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
			"process_type": "Sales Invoice",
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
			"process_type": "Purchase Invoice",
			"source_type": "Upload",
			"status": "Draft",
			"external_invoice_no": "DEMO-PURCHASE-001",
			"supplier": supplier,
			"notes": "Demo Draft Purchase VAT Process",
			"items": [{"item_text": "Vehicle cleaning service", "qty": 3, "rate": 40, "vat_rate": 15}],
		},
		{
			"process_type": "Sales Invoice",
			"source_type": "Scanner",
			"status": "Ready",
			"external_invoice_no": "DEMO-SALES-REVIEWED-001",
			"customer": customer,
			"notes": "Demo Ready Sales VAT Process",
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
			"customer_group": get_valid_default_customer_group(),
			"territory": get_valid_default_territory(),
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
