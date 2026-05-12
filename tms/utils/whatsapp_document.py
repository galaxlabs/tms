import traceback
from urllib.parse import quote

import frappe
from frappe.utils import now_datetime

from tms.utils.pdf_engine import generate_pdf, save_pdf
from tms.utils.whatsapp_utils import get_or_create_contact, normalize_phone
from tms.utils.zatca_invoice import (
	DEFAULT_ZATCA_PDFA_PRINT_FORMAT,
	generate_sales_invoice_pdfa_3b_bytes,
	resolve_sales_invoice_print_format,
)

PROFORMA_PRINT_FORMAT = "Profarma Invoice"
TRIP_PRINT_FORMAT = "Trip"
WHATSAPP_PDF_FOLDER = "Home/WhatsApp PDFs"
FALLBACK_PDF_FOLDER = "Home/Attachments"


@frappe.whitelist()
def send_document_pdf_via_whatsapp(
	doctype: str,
	name: str,
	to: str | None = None,
	print_format: str | None = None,
	caption: str | None = None,
):
	"""Generate a public PDF and send it as a WhatsApp document."""
	doc = frappe.get_doc(doctype, name)
	phone = _resolve_recipient(doc, to)
	if not phone:
		frappe.throw(f"WhatsApp number is missing for {doctype} {name}.")

	get_or_create_contact(whatsapp_id=phone, display_name=_recipient_display_name(doc))

	pdf_bytes, used_print_format = _generate_pdf_bytes(doc, print_format=print_format)
	file_url, file_name, file_id = _save_public_pdf(
		pdf_bytes,
		doctype,
		name,
	)

	message = caption or _default_caption(doc, used_print_format)
	msg = frappe.get_doc(
		{
			"doctype": "WhatsApp Message",
			"type": "Outgoing",
			"message_type": "Manual",
			"to": phone,
			"content_type": "document",
			"attach": file_url,
			"message": message,
			"reference_doctype": doctype,
			"reference_name": name,
		}
	)

	status = "Success"
	response_payload = ""
	try:
		msg.insert(ignore_permissions=True)
		status = getattr(msg, "status", None) or status
	except Exception:
		status = "Failed"
		response_payload = traceback.format_exc()

	_insert_send_log(
		reference_doctype=doctype,
		reference_name=name,
		to=phone,
		status=status,
		file_url=file_url,
		response_payload=response_payload,
	)

	if status.lower() != "success":
		frappe.throw("WhatsApp send failed. See WhatsApp Send Log / Error Log for details.")

	_mark_document_sent(doc, file_url, file_id)

	return {
		"status": "Success",
		"to": phone,
		"file_url": file_url,
		"file_name": file_name,
		"file_id": file_id,
		"print_format": used_print_format,
	}


@frappe.whitelist()
def send_sales_invoice_pdf_via_whatsapp(
	invoice_name: str,
	to: str | None = None,
	print_format: str | None = None,
	caption: str | None = None,
):
	return send_document_pdf_via_whatsapp(
		"Sales Invoice",
		invoice_name,
		to=to,
		print_format=print_format,
		caption=caption,
	)


@frappe.whitelist()
def send_proforma_invoice_via_whatsapp(
	invoice_name: str,
	to: str | None = None,
	caption: str | None = None,
):
	return send_document_pdf_via_whatsapp(
		"Sales Invoice",
		invoice_name,
		to=to,
		print_format=PROFORMA_PRINT_FORMAT,
		caption=caption,
	)


@frappe.whitelist()
def send_trip_pdf_via_whatsapp(trip_name: str, to: str | None = None, caption: str | None = None):
	return send_document_pdf_via_whatsapp(
		"Trip",
		trip_name,
		to=to,
		print_format=TRIP_PRINT_FORMAT,
		caption=caption,
	)


@frappe.whitelist()
def prepare_document_pdf_whatsapp_link(
	doctype: str,
	name: str,
	to: str | None = None,
	print_format: str | None = None,
	message: str | None = None,
):
	"""Generate a public PDF and return a wa.me link. No WhatsApp API is called."""
	doc = frappe.get_doc(doctype, name)
	phone = _resolve_recipient(doc, to)
	if not phone:
		frappe.throw(f"WhatsApp number is missing for {doctype} {name}.")

	pdf_bytes, used_print_format = _generate_pdf_bytes(doc, print_format=print_format)
	file_url, file_name, file_id = _save_public_pdf(
		pdf_bytes,
		doctype,
		name,
	)
	public_url = _absolute_file_url(file_url)
	text = message or _default_link_message(doc, public_url, used_print_format)

	_remember_pdf_attachment(doc, file_url, file_id)

	return {
		"status": "Ready",
		"to": phone,
		"file_url": file_url,
		"file_name": file_name,
		"file_id": file_id,
		"public_url": public_url,
		"whatsapp_url": f"https://wa.me/{phone}?text={quote(text)}",
		"print_format": used_print_format,
	}


@frappe.whitelist()
def prepare_trip_pdf_whatsapp_link(trip_name: str, to: str | None = None, message: str | None = None):
	return prepare_document_pdf_whatsapp_link(
		"Trip",
		trip_name,
		to=to,
		print_format=TRIP_PRINT_FORMAT,
		message=message,
	)


@frappe.whitelist()
def prepare_sales_invoice_pdf_whatsapp_link(
	invoice_name: str,
	to: str | None = None,
	print_format: str | None = None,
	message: str | None = None,
):
	return prepare_document_pdf_whatsapp_link(
		"Sales Invoice",
		invoice_name,
		to=to,
		print_format=print_format,
		message=message,
	)


@frappe.whitelist()
def prepare_proforma_invoice_whatsapp_link(
	invoice_name: str,
	to: str | None = None,
	message: str | None = None,
):
	return prepare_document_pdf_whatsapp_link(
		"Sales Invoice",
		invoice_name,
		to=to,
		print_format=PROFORMA_PRINT_FORMAT,
		message=message,
	)


def _generate_pdf_bytes(doc, print_format: str | None = None):
	if doc.doctype == "Sales Invoice":
		resolved_format = resolve_sales_invoice_print_format(doc, requested_format=print_format)
		if resolved_format == DEFAULT_ZATCA_PDFA_PRINT_FORMAT:
			pdf_bytes, used_print_format, _ = generate_sales_invoice_pdfa_3b_bytes(
				doc,
				print_format=resolved_format,
			)
			return pdf_bytes, used_print_format
		return generate_pdf(doc.doctype, doc.name, print_format=resolved_format), resolved_format

	return generate_pdf(doc.doctype, doc.name, print_format=print_format), print_format


def _save_public_pdf(pdf_bytes: bytes, doctype: str, name: str):
	try:
		return save_pdf(
			pdf_bytes,
			doctype,
			name,
			folder=WHATSAPP_PDF_FOLDER,
			public=True,
		)
	except frappe.LinkValidationError as exc:
		if WHATSAPP_PDF_FOLDER not in str(exc):
			raise

		return save_pdf(
			pdf_bytes,
			doctype,
			name,
			folder=FALLBACK_PDF_FOLDER,
			public=True,
		)


def _resolve_recipient(doc, explicit_to: str | None = None) -> str:
	if explicit_to:
		return normalize_phone(explicit_to)

	if doc.doctype == "Trip":
		return _resolve_trip_recipient(doc)

	for fieldname in (
		"contact_mobile",
		"contact_phone",
		"mobile_no",
		"phone",
		"customer_mobile",
		"customer_phone",
	):
		phone = normalize_phone(getattr(doc, fieldname, None))
		if phone:
			return phone

	if getattr(doc, "contact_person", None):
		phone = _get_first_value("Contact", doc.contact_person, ("mobile_no", "phone"))
		if phone:
			return phone

	if getattr(doc, "customer", None):
		phone = _get_first_value("Customer", doc.customer, ("mobile_no", "phone"))
		if phone:
			return phone

	return ""


def _resolve_trip_recipient(doc) -> str:
	if getattr(doc, "driver", None):
		phone = _get_first_value("Staff", doc.driver, ("mobile_no", "phone"))
		if phone:
			return phone

	for fieldname in ("driver_phone", "mobile_no", "phone"):
		phone = normalize_phone(getattr(doc, fieldname, None))
		if phone:
			return phone

	return ""


def _get_first_value(doctype: str, name: str, fieldnames: tuple[str, ...]) -> str:
	queryable_fields = _queryable_fields(doctype, fieldnames)
	if not queryable_fields:
		return ""

	values = frappe.db.get_value(doctype, name, queryable_fields, as_dict=True)
	if not values:
		return ""

	for fieldname in queryable_fields:
		phone = normalize_phone(values.get(fieldname))
		if phone:
			return phone

	return ""


def _queryable_fields(doctype: str, fieldnames: tuple[str, ...]) -> list[str]:
	try:
		meta = frappe.get_meta(doctype)
	except Exception:
		return []

	queryable = []
	for fieldname in fieldnames:
		try:
			if meta.has_field(fieldname) and frappe.db.has_column(doctype, fieldname):
				queryable.append(fieldname)
		except Exception:
			continue

	return queryable


def _recipient_display_name(doc) -> str:
	return (
		getattr(doc, "customer_name", None)
		or getattr(doc, "driver_name", None)
		or getattr(doc, "driver", None)
		or getattr(doc, "customer", None)
		or doc.name
	)


def _default_caption(doc, print_format: str | None = None) -> str:
	if print_format == PROFORMA_PRINT_FORMAT:
		return f"Proforma invoice {doc.name} PDF attached."
	if doc.doctype == "Sales Invoice":
		return f"Sales Invoice {doc.name} PDF attached."
	if doc.doctype == "Trip":
		return f"Trip {doc.name} PDF attached."
	return f"{doc.doctype} {doc.name} PDF attached."


def _default_link_message(doc, public_url: str, print_format: str | None = None) -> str:
	return f"{_default_caption(doc, print_format)}\n{public_url}"


def _absolute_file_url(file_url: str) -> str:
	if file_url.startswith(("http://", "https://")):
		return file_url

	return f"{frappe.utils.get_url().rstrip('/')}/{file_url.lstrip('/')}"


def _insert_send_log(reference_doctype, reference_name, to, status, file_url, response_payload=""):
	if not frappe.db.exists("DocType", "WhatsApp Send Log"):
		return

	frappe.get_doc(
		{
			"doctype": "WhatsApp Send Log",
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
			"to": to,
			"message_type": "Document",
			"status": status,
			"file_link": file_url,
			"response_json": response_payload,
			"sent_at": now_datetime(),
		}
	).insert(ignore_permissions=True)


def _mark_document_sent(doc, file_url: str, file_id: str):
	_remember_pdf_attachment(doc, file_url, file_id)

	if doc.doctype == "Trip" and hasattr(doc, "kashf_sent") and not doc.kashf_sent:
		doc.db_set("kashf_sent", 1)
		doc.add_comment("Info", f"Kashf PDF sent successfully at {now_datetime()}")


def _remember_pdf_attachment(doc, file_url: str, file_id: str):
	if hasattr(doc, "last_pdf_url"):
		doc.db_set("last_pdf_url", file_url, update_modified=False)
	if hasattr(doc, "last_pdf_file"):
		doc.db_set("last_pdf_file", file_id, update_modified=False)
