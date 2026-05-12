from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import frappe
from frappe.tests.utils import FrappeTestCase


class TestWhatsAppDocument(FrappeTestCase):
	def test_send_document_pdf_saves_public_pdf_and_inserts_whatsapp_document(self):
		from tms.utils.whatsapp_document import send_document_pdf_via_whatsapp

		source_doc = SimpleNamespace(
			doctype="Sales Invoice",
			name="SINV-0001",
			company="CELTC",
			contact_mobile="+966 55-123-4567",
		)
		message_doc = SimpleNamespace(
			name="WA-0001",
			status="Success",
			insert=lambda ignore_permissions=True: None,
		)
		created_docs = []

		def fake_get_doc(*args):
			if args == ("Sales Invoice", "SINV-0001"):
				return source_doc
			if len(args) == 1 and isinstance(args[0], dict):
				created_docs.append(args[0])
				return message_doc
			raise AssertionError(f"Unexpected get_doc args: {args}")

		with patch("tms.utils.whatsapp_document.frappe.get_doc", side_effect=fake_get_doc), \
			patch("tms.utils.whatsapp_document.get_or_create_contact"), \
			patch("tms.utils.whatsapp_document.generate_pdf", return_value=b"%PDF-1.4"), \
			patch("tms.utils.whatsapp_document.save_pdf", return_value=("/files/SINV-0001.pdf", "SINV-0001.pdf", "FILE-0001")), \
			patch("tms.utils.whatsapp_document._insert_send_log"):
			result = send_document_pdf_via_whatsapp("Sales Invoice", "SINV-0001")

		self.assertEqual(result["status"], "Success")
		self.assertEqual(result["to"], "966551234567")
		self.assertEqual(result["file_url"], "/files/SINV-0001.pdf")

		self.assertEqual(len(created_docs), 1)
		self.assertEqual(created_docs[0]["doctype"], "WhatsApp Message")
		self.assertEqual(created_docs[0]["type"], "Outgoing")
		self.assertEqual(created_docs[0]["message_type"], "Manual")
		self.assertEqual(created_docs[0]["content_type"], "document")
		self.assertEqual(created_docs[0]["to"], "966551234567")
		self.assertEqual(created_docs[0]["attach"], "/files/SINV-0001.pdf")
		self.assertEqual(created_docs[0]["reference_doctype"], "Sales Invoice")
		self.assertEqual(created_docs[0]["reference_name"], "SINV-0001")

	def test_proforma_wrapper_uses_proforma_print_format(self):
		from tms.utils.whatsapp_document import send_proforma_invoice_via_whatsapp

		with patch("tms.utils.whatsapp_document.send_document_pdf_via_whatsapp", return_value={"status": "Success"}) as sender:
			result = send_proforma_invoice_via_whatsapp("SINV-0001", to="+966500000000")

		self.assertEqual(result["status"], "Success")
		sender.assert_called_once_with(
			"Sales Invoice",
			"SINV-0001",
			to="+966500000000",
			print_format="Profarma Invoice",
			caption=None,
		)

	def test_prepare_trip_whatsapp_link_uses_staff_mobile_without_api_message(self):
		from tms.utils.whatsapp_document import prepare_trip_pdf_whatsapp_link

		trip_doc = SimpleNamespace(doctype="Trip", name="TRIP-0001", driver="DRV-0001")

		class FakeMeta:
			def has_field(self, fieldname):
				return fieldname in ("mobile_no", "phone")

		with patch("tms.utils.whatsapp_document.frappe.get_doc", return_value=trip_doc), \
			patch("tms.utils.whatsapp_document.frappe.get_meta", return_value=FakeMeta()), \
			patch("tms.utils.whatsapp_document.frappe.db.has_column", return_value=True), \
			patch("tms.utils.whatsapp_document.frappe.db.get_value", return_value={"mobile_no": "+966 57-240-5550", "phone": None}), \
			patch("tms.utils.whatsapp_document.frappe.utils.get_url", return_value="https://tms.example.com"), \
			patch("tms.utils.whatsapp_document.generate_pdf", return_value=b"%PDF-1.4"), \
			patch("tms.utils.whatsapp_document.save_pdf", return_value=("/files/Trip-TRIP-0001.pdf", "Trip-TRIP-0001.pdf", "FILE-0001")):
			result = prepare_trip_pdf_whatsapp_link("TRIP-0001")

		self.assertEqual(result["status"], "Ready")
		self.assertEqual(result["to"], "966572405550")
		self.assertEqual(result["file_url"], "/files/Trip-TRIP-0001.pdf")
		self.assertEqual(result["public_url"], "https://tms.example.com/files/Trip-TRIP-0001.pdf")
		self.assertTrue(result["whatsapp_url"].startswith("https://wa.me/966572405550?text="))

		query = parse_qs(urlparse(result["whatsapp_url"]).query)
		self.assertIn("https://tms.example.com/files/Trip-TRIP-0001.pdf", query["text"][0])

	def test_save_public_pdf_falls_back_when_whatsapp_folder_is_missing(self):
		from tms.utils.whatsapp_document import _save_public_pdf

		calls = []

		def fake_save_pdf(*args, **kwargs):
			calls.append(kwargs["folder"])
			if kwargs["folder"] == "Home/WhatsApp PDFs":
				frappe.throw("Could not find Folder: Home/WhatsApp PDFs", frappe.LinkValidationError)
			return "/files/doc.pdf", "doc.pdf", "FILE-0001"

		with patch("tms.utils.whatsapp_document.save_pdf", side_effect=fake_save_pdf):
			result = _save_public_pdf(b"%PDF-1.4", "Trip", "TRIP-0001")

		self.assertEqual(result, ("/files/doc.pdf", "doc.pdf", "FILE-0001"))
		self.assertEqual(calls, ["Home/WhatsApp PDFs", "Home/Attachments"])

	def test_get_first_value_skips_fields_missing_from_table(self):
		from tms.utils.whatsapp_document import _get_first_value

		class FakeMeta:
			def has_field(self, fieldname):
				return fieldname == "mobile_no"

		with patch("tms.utils.whatsapp_document.frappe.get_meta", return_value=FakeMeta()), \
			patch("tms.utils.whatsapp_document.frappe.db.has_column", side_effect=lambda doctype, fieldname: fieldname == "mobile_no"), \
			patch("tms.utils.whatsapp_document.frappe.db.get_value", return_value={"mobile_no": "+966 50 000 0000"}) as get_value:
			result = _get_first_value("Customer", "CUST-0001", ("mobile_no", "phone"))

		self.assertEqual(result, "966500000000")
		get_value.assert_called_once_with("Customer", "CUST-0001", ["mobile_no"], as_dict=True)
