# Copyright (c) 2026, Galaxy Labs and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today
from frappe.utils.file_manager import save_file
from unittest.mock import patch

from tms.transport_management_system.api.vat_dashboard import (
	_build_invoice_conditions,
	_get_invoice_date_expression,
	get_vat_dashboard_data,
)
from tms.transport_management_system.doctype.vat_process.vat_process import (
	VATProcess,
	_update_created_document_for_doc,
	attach_existing_file_to_vat_process,
	create_erpnext_document,
	create_document_from_vat_process,
	create_vat_process_from_upload,
	get_source_file_url,
	get_target_doctype,
	get_vat_process_attachments,
	update_created_document,
)
from tms.utils.party_defaults import get_valid_default_customer_group, get_valid_default_supplier_group, get_valid_default_territory


class TestVATProcess(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.reload_doc("transport_management_system", "doctype", "vat_process_item")
		frappe.reload_doc("transport_management_system", "doctype", "vat_process")

	def test_vat_process_doctype_exists(self):
		self.assertTrue(frappe.db.exists("DocType", "VAT Process"))

	def test_validate_calculates_item_and_parent_totals(self):
		doc = frappe.get_doc(
			{
				"doctype": "VAT Process",
				"process_type": "Sales Invoice",
				"company": get_test_company(),
				"posting_date": today(),
				"status": "Draft",
				"items": [
					{
						"item_text": "Consulting",
						"qty": 2,
						"rate": 100,
						"vat_rate": 15,
					}
				],
			}
		)

		doc.validate()

		self.assertEqual(doc.items[0].amount, 200)
		self.assertEqual(doc.items[0].vat_amount, 30)
		self.assertEqual(doc.items[0].total_amount, 230)
		self.assertEqual(doc.net_total, 200)
		self.assertEqual(doc.vat_amount, 30)
		self.assertEqual(doc.grand_total, 230)

	def test_validate_calculates_lump_sum_item_rate_and_totals(self):
		doc = frappe.get_doc(
			{
				"doctype": "VAT Process",
				"process_type": "Purchase Order",
				"company": get_test_company(),
				"posting_date": today(),
				"status": "Draft",
				"items": [
					{
						"item_text": "Problem identification of transducers",
						"calculation_type": "Lump Sum Amount",
						"qty": 11,
						"uom": "Nos",
						"lump_sum_amount": 550000,
						"vat_rate": 15,
					}
				],
			}
		)

		doc.validate()

		self.assertEqual(doc.items[0].rate, 50000)
		self.assertEqual(doc.items[0].amount, 550000)
		self.assertEqual(doc.items[0].vat_amount, 82500)
		self.assertEqual(doc.items[0].total_amount, 632500)

	def test_calculate_totals_applies_discount_and_airfreight(self):
		doc = frappe.get_doc(
			{
				"doctype": "VAT Process",
				"process_type": "Purchase Order",
				"company": get_test_company(),
				"posting_date": today(),
				"status": "Draft",
				"discount_amount": 10,
				"airfreight_charges": 5,
				"rounding_adjustment": 2,
				"items": [
					{
						"item_text": "Service Line",
						"qty": 2,
						"rate": 100,
						"vat_rate": 15,
					}
				],
			}
		)

		doc.validate()

		self.assertEqual(doc.net_total, 200)
		self.assertEqual(doc.vat_amount, 30)
		self.assertEqual(doc.grand_total, 227)

	@patch.object(VATProcess, "_apply_manual_template_taxes")
	@patch.object(VATProcess, "_set_default_tax_template")
	@patch("frappe.model.document.Document.insert", autospec=True, side_effect=lambda self, *args, **kwargs: self)
	def test_create_purchase_order_maps_lump_sum_rows_and_terms(
		self, _mock_insert, mock_set_default_tax_template, mock_apply_manual_template_taxes
	):
		terms_doc = get_test_terms_and_conditions()
		doc = frappe.get_doc(
			{
				"doctype": "VAT Process",
				"process_type": "Purchase Order",
				"company": get_test_company(),
				"posting_date": today(),
				"required_by_date": add_days(today(), 7),
				"supplier": get_test_supplier(),
				"currency": "SAR",
				"status": "Ready",
				"tc_name": terms_doc.name,
				"items": [
					{
						"item_text": "Problem identification of transducers installed at different Grid Stations in Sakaka as per provided list",
						"calculation_type": "Lump Sum Amount",
						"qty": 11,
						"uom": "Nos",
						"lump_sum_amount": 550000,
						"vat_rate": 15,
					},
					{
						"item_text": "Mob/Demob charges: Applied only per visit where work is executed and performed",
						"calculation_type": "Lump Sum Amount",
						"qty": 1,
						"lump_sum_amount": 0,
						"vat_rate": 15,
					},
				],
			}
		)
		doc.validate()
		mock_set_default_tax_template.return_value = None

		purchase_order = doc.create_purchase_order()

		self.assertEqual(purchase_order.supplier, doc.supplier)
		self.assertEqual(str(purchase_order.schedule_date), str(doc.required_by_date))
		self.assertEqual(purchase_order.tc_name, terms_doc.name)
		self.assertEqual(purchase_order.items[0].qty, 11)
		self.assertEqual(purchase_order.items[0].rate, 50000)
		self.assertEqual(purchase_order.items[0].amount, 550000)
		self.assertEqual(str(purchase_order.items[0].schedule_date), str(doc.required_by_date))
		self.assertEqual(purchase_order.items[1].uom, "Nos")
		self.assertEqual(purchase_order.items[1].rate, 0)
		self.assertEqual(purchase_order.items[1].amount, 0)
		mock_apply_manual_template_taxes.assert_called_once()

	def test_validate_invoice_creation_allowed_requires_ready_status(self):
		doc = frappe.get_doc(
			{
				"doctype": "VAT Process",
				"process_type": "Sales Invoice",
				"company": get_test_company(),
				"posting_date": today(),
				"customer": get_test_customer(),
				"status": "Draft",
				"items": [{"item_text": "Consulting", "qty": 1, "rate": 10}],
			}
		)

		with self.assertRaises(frappe.ValidationError):
			doc.validate_invoice_creation_allowed()

	def test_validate_requires_process_type(self):
		doc = frappe.get_doc(
			{
				"doctype": "VAT Process",
				"company": get_test_company(),
				"source_type": "Scanner",
				"source_document": "/files/sample-scan.jpg",
				"posting_date": today(),
				"status": "Draft",
			}
		)

		with self.assertRaises(frappe.ValidationError):
			doc.validate()

	def test_attach_existing_file_to_vat_process_sets_primary_source_document(self):
		doc = make_vat_process_doc().insert(ignore_permissions=True)
		file_doc = save_file(
			"vat-process-test.txt",
			b"vat upload",
			dt=None,
			dn=None,
			is_private=1,
		)

		result = attach_existing_file_to_vat_process(doc.name, file_url=file_doc.file_url)

		doc.reload()
		attached_file = frappe.get_doc("File", result["file_name"])
		self.assertEqual(doc.source_document, file_doc.file_url)
		self.assertEqual(attached_file.attached_to_doctype, "VAT Process")
		self.assertEqual(attached_file.attached_to_name, doc.name)

	def test_create_vat_process_from_upload_creates_doc_and_attachment(self):
		file_doc = save_file(
			"vat-process-created.txt",
			b"vat upload create",
			dt=None,
			dn=None,
			is_private=1,
		)

		result = create_vat_process_from_upload(
			process_type="Purchase",
			company=get_test_company(),
			supplier=get_test_supplier(),
			file_url=file_doc.file_url,
			source_type="Upload",
		)

		doc = frappe.get_doc("VAT Process", result["name"])
		self.assertEqual(doc.process_type, "Purchase Invoice")
		self.assertEqual(doc.source_type, "Upload")
		self.assertEqual(doc.source_document, file_doc.file_url)
		self.assertTrue(
			frappe.db.exists(
				"File",
				{
					"attached_to_doctype": "VAT Process",
					"attached_to_name": doc.name,
					"file_url": file_doc.file_url,
				},
			)
		)

	def test_get_vat_process_attachments_returns_attached_files(self):
		doc = make_vat_process_doc().insert(ignore_permissions=True)
		file_doc = save_file(
			"vat-process-list.txt",
			b"vat upload list",
			dt="VAT Process",
			dn=doc.name,
			is_private=1,
		)

		result = get_vat_process_attachments(doc.name)

		self.assertEqual(result["count"], 1)
		self.assertEqual(result["attachments"][0]["file_url"], file_doc.file_url)

	def test_create_missing_items_sets_item_default_company(self):
		item_meta = frappe.get_meta("Item")
		if not item_meta.has_field("item_defaults"):
			self.skipTest("Item defaults child table is not available in this site")

		doc = frappe.get_doc(
			{
				"doctype": "VAT Process",
				"process_type": "Sales Invoice",
				"company": get_test_company(),
				"posting_date": today(),
				"status": "Draft",
				"items": [
					{
						"item_text": f"Demo Service {frappe.generate_hash(length=6)}",
						"qty": 1,
						"rate": 10,
					}
				],
			}
		)

		doc.create_missing_items()

		item_doc = frappe.get_doc("Item", doc.items[0].item_code)
		self.assertTrue(any(row.company == doc.company for row in (item_doc.item_defaults or [])))

	def test_validate_uses_selected_company_and_purchase_invoice_scan_party_fields(self):
		company = get_test_company()
		company_name_arabic = frappe.db.get_value("Company", company, "company_name_arabic")

		doc = frappe.get_doc(
			{
				"doctype": "VAT Process",
				"process_type": "Purchase Invoice",
				"company": company,
				"posting_date": today(),
				"status": "Draft",
				"issuer_name_text": "Sama Taiba Company",
				"issuer_name_arabic": "شركة سما طيبة",
				"issuer_vat_no": "311531689900003",
				"document_customer_name_text": company,
				"document_customer_name_arabic": company_name_arabic,
				"document_customer_vat_no": frappe.db.get_value("Company", company, "tax_id"),
			}
		)

		doc.validate()

		self.assertEqual(doc.company, company)
		self.assertEqual(doc.party_name_text, "Sama Taiba Company")
		self.assertEqual(doc.party_name_arabic, "شركة سما طيبة")
		self.assertEqual(doc.party_vat_no, "311531689900003")

	@patch.object(VATProcess, "_get_first_company_template")
	@patch.object(VATProcess, "_get_company_template_matching_rate")
	@patch("frappe.db.get_value")
	def test_get_company_tax_template_falls_back_to_company_default(
		self, mock_get_value, mock_get_company_template_matching_rate, mock_get_first_company_template
	):
		doc = make_vat_process_doc()
		doc.company = get_test_company()
		mock_get_value.return_value = None
		mock_get_company_template_matching_rate.return_value = None
		mock_get_first_company_template.return_value = "KSA Tax - Demo"

		template = doc._get_tax_template_for_invoice("Sales Invoice", None, "Customer", "sales_taxes_and_charges_template")

		self.assertEqual(template, ("KSA Tax - Demo", "Sales Taxes and Charges Template"))

	@patch.object(VATProcess, "_apply_manual_template_taxes")
	@patch.object(VATProcess, "_get_tax_template_for_invoice")
	def test_set_default_tax_template_uses_manual_fallback_for_purchase_when_sales_template_matches(
		self, mock_get_tax_template_for_invoice, mock_apply_manual_template_taxes
	):
		doc = make_vat_process_doc()
		doc.company = get_test_company()
		doc.vat_rate = 15
		invoice = frappe.get_doc({"doctype": "Purchase Invoice", "company": doc.company, "supplier": get_test_supplier()})
		mock_get_tax_template_for_invoice.return_value = ("KSA Tax - CELTC", "Sales Taxes and Charges Template")

		manual_template = doc._set_default_tax_template(
			invoice, get_test_supplier(), "Supplier", "purchase_taxes_and_charges_template"
		)
		doc._apply_manual_template_taxes(invoice, manual_template)

		self.assertFalse(invoice.get("taxes_and_charges"))
		mock_apply_manual_template_taxes.assert_called_once_with(
			invoice, ("KSA Tax - CELTC", "Sales Taxes and Charges Template")
		)

	def test_build_invoice_conditions_supports_live_and_submitted_modes(self):
		live_filters = frappe._dict(company=get_test_company(), from_date="2026-01-01", to_date="2026-01-31", document_mode="live")
		submitted_filters = frappe._dict(
			company=get_test_company(), from_date="2026-01-01", to_date="2026-01-31", document_mode="submitted"
		)

		live_conditions, _live_values = _build_invoice_conditions(live_filters)
		submitted_conditions, _submitted_values = _build_invoice_conditions(submitted_filters)

		self.assertIn("docstatus < 2", live_conditions)
		self.assertIn("docstatus = 1", submitted_conditions)

	def test_get_invoice_date_expression_prefers_bill_date_for_purchase_invoice(self):
		self.assertEqual(_get_invoice_date_expression("Purchase Invoice"), "COALESCE(bill_date, posting_date)")
		self.assertEqual(_get_invoice_date_expression("Sales Invoice"), "posting_date")

	@patch("tms.transport_management_system.doctype.vat_process.vat_process.extract_vat_invoice_with_gemini")
	@patch("tms.transport_management_system.doctype.vat_process.vat_process.OCRManager")
	def test_analyze_source_document_with_gemini_updates_vat_process(
		self, mock_ocr_manager, mock_extract_vat_invoice_with_gemini
	):
		doc = make_vat_process_doc().insert(ignore_permissions=True)
		doc.process_type = "Purchase Invoice"
		file_doc = save_file("test-vat-invoice.txt", b"test image", dt="VAT Process", dn=doc.name, is_private=0)
		doc.source_document = file_doc.file_url
		doc.save(ignore_permissions=True)

		mock_ocr = mock_ocr_manager.return_value
		mock_ocr.extract_raw_text.return_value = ("invoice ocr text", "gvision")
		mock_extract_vat_invoice_with_gemini.return_value = {
			"issuer_name_text": "Sama Taiba Company",
			"issuer_name_arabic": "شركة سما طيبة",
			"issuer_vat_no": "311531689900003",
			"document_customer_name_text": get_test_company(),
			"document_customer_name_arabic": frappe.db.get_value("Company", get_test_company(), "company_name_arabic"),
			"document_customer_vat_no": frappe.db.get_value("Company", get_test_company(), "tax_id"),
			"external_invoice_no": f"TEST-{frappe.generate_hash(length=8)}",
			"invoice_date": "2026-03-08",
			"vat_rate": 15,
			"confidence": 91,
			"items": [
				{
					"item_text": "LUX SOAP S 6*12*75 GM",
					"qty": 4,
					"rate": 11.30,
					"vat_rate": 15,
				}
			],
		}

		result = frappe.get_doc("VAT Process", doc.name).analyze_source_document_with_gemini()

		reloaded = frappe.get_doc("VAT Process", doc.name)
		self.assertEqual(reloaded.process_type, "Purchase Invoice")
		self.assertEqual(reloaded.company, get_test_company())
		self.assertEqual(reloaded.party_name_text, "Sama Taiba Company")
		self.assertTrue(reloaded.external_invoice_no.startswith("TEST-"))
		self.assertEqual(str(reloaded.invoice_date), "2026-03-08")
		self.assertEqual(reloaded.items[0].item_text, "LUX SOAP S 6*12*75 GM")
		self.assertEqual(reloaded.extraction_status, "Extracted")
		self.assertEqual(reloaded.source_document, file_doc.file_url)
		self.assertEqual(result["process_type"], "Purchase Invoice")
		self.assertEqual(result["file_url"], file_doc.file_url)
		self.assertEqual(result["ocr_engine"], "gvision")

	@patch("tms.transport_management_system.doctype.vat_process.vat_process.extract_vat_invoice_with_gemini")
	@patch("tms.transport_management_system.doctype.vat_process.vat_process.OCRManager")
	def test_analyze_source_document_with_gemini_does_not_create_duplicate_files(
		self, mock_ocr_manager, mock_extract_vat_invoice_with_gemini
	):
		file_doc = save_file("vat-source-reuse.txt", b"reuse me", dt=None, dn=None, is_private=1)
		doc = make_vat_process_doc().insert(ignore_permissions=True)
		doc.process_type = "Purchase Invoice"
		doc.review_status = "Draft"
		doc.save(ignore_permissions=True)
		attach_existing_file_to_vat_process(doc.name, file_url=file_doc.file_url)

		mock_ocr = mock_ocr_manager.return_value
		mock_ocr.extract_raw_text.return_value = ("invoice ocr text", "gvision")
		mock_extract_vat_invoice_with_gemini.return_value = {"external_invoice_no": "REUSE-001", "items": []}

		before_count = frappe.db.count("File", {"file_url": file_doc.file_url})
		for _index in range(3):
			frappe.get_doc("VAT Process", doc.name).analyze_source_document_with_gemini()
		after_count = frappe.db.count("File", {"file_url": file_doc.file_url})

		self.assertEqual(before_count, after_count)

	def test_get_target_doctype_maps_process_types(self):
		doc = make_vat_process_doc()
		doc.process_type = "Purchase Invoice"
		self.assertEqual(get_target_doctype(doc), "Purchase Invoice")
		doc.process_type = "Proforma Invoice"
		self.assertEqual(get_target_doctype(doc), "Sales Order")
		doc.process_type = "Sales Quotation"
		self.assertEqual(get_target_doctype(doc), "Quotation")

	def test_get_source_file_url_uses_existing_source_document(self):
		doc = make_vat_process_doc()
		doc.source_document = "/files/demo-source.pdf"
		self.assertEqual(get_source_file_url(doc), "/files/demo-source.pdf")

	@patch("tms.transport_management_system.api.vat_dashboard._query_top_parties")
	@patch("tms.transport_management_system.api.vat_dashboard._query_vat_process_status_rows")
	@patch("tms.transport_management_system.api.vat_dashboard._query_invoice_month_rows")
	@patch("tms.transport_management_system.api.vat_dashboard._query_invoice_summary")
	def test_get_vat_dashboard_data_builds_expected_totals_and_alert(
		self,
		mock_invoice_summary,
		mock_invoice_month_rows,
		mock_status_rows,
		mock_top_parties,
	):
		mock_invoice_summary.side_effect = [
			{"invoice_count": 2, "net_total": 1000, "vat_total": 150, "grand_total": 1150},
			{"invoice_count": 1, "net_total": 600, "vat_total": 90, "grand_total": 690},
		]
		mock_invoice_month_rows.side_effect = [
			[
				{"month_key": "2026-01", "month_label": "Jan 2026", "net_total": 600, "vat_total": 90},
				{"month_key": "2026-02", "month_label": "Feb 2026", "net_total": 400, "vat_total": 60},
			],
			[
				{"month_key": "2026-01", "month_label": "Jan 2026", "net_total": 300, "vat_total": 45},
				{"month_key": "2026-02", "month_label": "Feb 2026", "net_total": 300, "vat_total": 45},
			],
		]
		mock_status_rows.return_value = [
			{"status": "Needs Review", "count": 2, "grand_total": 500},
			{"status": "Invoice Created", "count": 1, "grand_total": 1150},
		]
		mock_top_parties.side_effect = [
			[{"party": "Customer A", "net_total": 1000, "vat_total": 150}],
			[{"party": "Supplier A", "net_total": 600, "vat_total": 90}],
		]

		result = get_vat_dashboard_data(
			company=get_test_company(),
			from_date="2026-01-01",
			to_date="2026-02-28",
		)

		self.assertEqual(result["totals"]["sales_invoice_amount"], 1150)
		self.assertEqual(result["totals"]["purchase_invoice_amount"], 690)
		self.assertEqual(result["totals"]["total_collected_vat_amount"], 150)
		self.assertEqual(result["totals"]["total_paid_vat_amount"], 90)
		self.assertEqual(result["totals"]["invoice_amount_difference"], 460)
		self.assertEqual(result["totals"]["vat_balance_difference"], 60)
		self.assertEqual(result["totals"]["vat_collected"], 150)
		self.assertEqual(result["totals"]["vat_paid"], 90)
		self.assertEqual(result["totals"]["net_vat_payable"], 60)
		self.assertEqual(result["filters"]["document_mode"], "live")
		self.assertEqual(result["audit_signal"]["level"], "red")
		self.assertEqual(result["charts"]["vat_trend"]["labels"], ["Jan 2026", "Feb 2026"])
		self.assertEqual(result["charts"]["status_distribution"]["labels"], ["Needs Review", "Invoice Created"])
		self.assertEqual(result["top_parties"]["customers"][0]["party"], "Customer A")

	@patch("tms.transport_management_system.api.vat_dashboard._query_top_parties")
	@patch("tms.transport_management_system.api.vat_dashboard._query_vat_process_status_rows")
	@patch("tms.transport_management_system.api.vat_dashboard._query_invoice_month_rows")
	@patch("tms.transport_management_system.api.vat_dashboard._query_invoice_summary")
	def test_get_vat_dashboard_data_marks_safe_when_purchase_vat_covers_sales_vat(
		self,
		mock_invoice_summary,
		mock_invoice_month_rows,
		mock_status_rows,
		mock_top_parties,
	):
		mock_invoice_summary.side_effect = [
			{"invoice_count": 1, "net_total": 500, "vat_total": 75, "grand_total": 575},
			{"invoice_count": 2, "net_total": 900, "vat_total": 135, "grand_total": 1035},
		]
		mock_invoice_month_rows.side_effect = [[], []]
		mock_status_rows.return_value = []
		mock_top_parties.side_effect = [[], []]

		result = get_vat_dashboard_data(
			company=get_test_company(),
			from_date="2026-01-01",
			to_date="2026-01-31",
		)

		self.assertEqual(result["totals"]["net_vat_payable"], -60)
		self.assertEqual(result["audit_signal"]["level"], "green")
		self.assertIn("covers", result["audit_signal"]["message"].lower())

	def test_set_default_tax_template_creates_company_purchase_template_when_missing(self):
		doc = make_vat_process_doc()
		doc.company = get_test_company()
		doc.vat_rate = 15
		template_name = "KSA VAT 15% - CELTC"
		if frappe.db.exists("Purchase Taxes and Charges Template", template_name):
			frappe.delete_doc("Purchase Taxes and Charges Template", template_name, force=1)

		invoice = frappe.get_doc({"doctype": "Purchase Invoice", "company": doc.company, "supplier": get_test_supplier()})

		doc._set_default_tax_template(invoice, None, "Supplier", "purchase_taxes_and_charges_template")

		self.assertEqual(invoice.taxes_and_charges, template_name)
		template_doc = frappe.get_doc("Purchase Taxes and Charges Template", template_name)
		self.assertEqual(template_doc.company, doc.company)
		self.assertEqual(template_doc.title, "KSA VAT 15%")

	@patch.object(VATProcess, "_sync_created_document_link_state", return_value=False)
	@patch.object(VATProcess, "_validate_links")
	@patch.object(VATProcess, "create_purchase_order")
	def test_create_document_from_vat_process_dispatches_purchase_order(
		self, mock_create_purchase_order, _mock_validate_links, _mock_sync_state
	):
		mock_create_purchase_order.return_value = frappe._dict(doctype="Purchase Order", name="PUR-ORD-TEST-0001")
		doc = frappe.get_doc(
			{
				"doctype": "VAT Process",
				"process_type": "Purchase Order",
				"company": get_test_company(),
				"posting_date": today(),
				"supplier": get_test_supplier(),
				"status": "Ready",
				"items": [{"item_text": "Service Line", "qty": 1, "rate": 100}],
			}
		).insert(ignore_permissions=True)

		result = create_document_from_vat_process(doc.name)
		reloaded = frappe.get_doc("VAT Process", doc.name)

		self.assertEqual(result["doctype"], "Purchase Order")
		self.assertEqual(reloaded.created_purchase_order, "PUR-ORD-TEST-0001")
		self.assertEqual(reloaded.created_doctype, "Purchase Order")
		self.assertEqual(reloaded.created_document, "PUR-ORD-TEST-0001")
		self.assertEqual(reloaded.status, "Document Created")

	@patch.object(VATProcess, "_sync_created_document_link_state", return_value=False)
	@patch.object(VATProcess, "_validate_links")
	@patch.object(VATProcess, "create_quotation")
	def test_create_document_from_vat_process_dispatches_quotation(self, mock_create_quotation, _mock_validate_links, _mock_sync_state):
		mock_create_quotation.return_value = frappe._dict(doctype="Quotation", name="QTN-TEST-0001")
		doc = frappe.get_doc(
			{
				"doctype": "VAT Process",
				"process_type": "Sales Quotation",
				"company": get_test_company(),
				"posting_date": today(),
				"customer": get_test_customer(),
				"status": "Ready",
				"review_status": "Ready",
				"items": [{"item_text": "Quoted Service", "qty": 1, "rate": 250}],
			}
		).insert(ignore_permissions=True)

		result = create_document_from_vat_process(doc.name)
		reloaded = frappe.get_doc("VAT Process", doc.name)

		self.assertEqual(result["doctype"], "Quotation")
		self.assertEqual(reloaded.created_quotation, "QTN-TEST-0001")
		self.assertEqual(reloaded.created_doctype, "Quotation")
		self.assertEqual(reloaded.created_document, "QTN-TEST-0001")
		self.assertEqual(reloaded.status, "Document Created")

	@patch.object(VATProcess, "_sync_created_document_link_state", return_value=False)
	@patch.object(VATProcess, "_validate_links")
	@patch.object(VATProcess, "create_sales_order")
	def test_create_erpnext_document_dispatches_proforma_to_sales_order(self, mock_create_sales_order, _mock_validate_links, _mock_sync_state):
		mock_create_sales_order.return_value = frappe._dict(doctype="Sales Order", name="SAL-ORD-TEST-0001")
		doc = frappe.get_doc(
			{
				"doctype": "VAT Process",
				"process_type": "Proforma Invoice",
				"company": get_test_company(),
				"posting_date": today(),
				"customer": get_test_customer(),
				"status": "Ready",
				"review_status": "Ready",
				"items": [{"item_text": "Proforma Service", "qty": 1, "rate": 250}],
			}
		).insert(ignore_permissions=True)

		result = create_erpnext_document(doc.name)
		reloaded = frappe.get_doc("VAT Process", doc.name)

		self.assertEqual(result["doctype"], "Sales Order")
		self.assertEqual(reloaded.created_document_type, "Sales Order")
		self.assertEqual(reloaded.created_document, "SAL-ORD-TEST-0001")
		self.assertEqual(reloaded.review_status, "Document Created")


	def test_sync_created_document_link_state_clears_missing_document_and_sets_ready(self):
		doc = frappe.get_doc(
			{
				"doctype": "VAT Process",
				"process_type": "Purchase Order",
				"company": get_test_company(),
				"posting_date": today(),
				"supplier": get_test_supplier(),
				"status": "Document Created",
				"review_status": "Document Created",
				"created_document_type": "Purchase Order",
				"created_document": "PUR-ORD-MISSING-0001",
				"created_purchase_order": "PUR-ORD-MISSING-0001",
				"items": [{"item_text": "Service Line", "qty": 1, "rate": 100}],
			}
		)

		changed = doc._sync_created_document_link_state()

		self.assertTrue(changed)
		self.assertEqual(doc.created_document_type, "")
		self.assertEqual(doc.created_document, "")
		self.assertEqual(doc.created_purchase_order, "")
		self.assertEqual(doc.status, "Ready")
		self.assertEqual(doc.review_status, "Ready")

	def test_update_created_document_dispatches_existing_purchase_order(self):
		doc = frappe.get_doc(
			{
				"doctype": "VAT Process",
				"process_type": "Purchase Order",
				"company": get_test_company(),
				"posting_date": today(),
				"supplier": get_test_supplier(),
				"status": "Document Created",
				"review_status": "Document Created",
				"created_document_type": "Purchase Order",
				"created_document": "PUR-ORD-TEST-0001",
				"created_purchase_order": "PUR-ORD-TEST-0001",
				"items": [{"item_text": "Service Line", "qty": 1, "rate": 100}],
			}
		).insert(ignore_permissions=True)

		existing_document = frappe._dict(doctype="Purchase Order", name="PUR-ORD-TEST-0001", docstatus=0)
		original_get_doc = frappe.get_doc

		with patch.object(VATProcess, "_sync_created_document_link_state", return_value=False), \
			 patch.object(VATProcess, "_get_created_document_reference", return_value=("Purchase Order", "PUR-ORD-TEST-0001")), \
			 patch.object(VATProcess, "update_purchase_order", return_value=existing_document) as mock_update_purchase_order, \
			 patch("tms.transport_management_system.doctype.vat_process.vat_process.validate_before_create") as mock_validate_before_create, \
			 patch("tms.transport_management_system.doctype.vat_process.vat_process.frappe.get_doc", side_effect=lambda doctype, name=None, *args, **kwargs: existing_document if doctype == "Purchase Order" and name == "PUR-ORD-TEST-0001" else original_get_doc(doctype, name, *args, **kwargs)):
			result = _update_created_document_for_doc(doc)

		reloaded = frappe.get_doc("VAT Process", doc.name)

		mock_validate_before_create.assert_called_once()
		mock_update_purchase_order.assert_called_once()
		self.assertEqual(result["doctype"], "Purchase Order")
		self.assertTrue(result["updated"])
		self.assertEqual(reloaded.created_document, "PUR-ORD-TEST-0001")
		self.assertEqual(reloaded.review_status, "Document Created")


def make_vat_process_doc():
	return frappe.get_doc(
		{
			"doctype": "VAT Process",
			"process_type": "Sales Invoice",
			"company": get_test_company(),
			"posting_date": today(),
			"status": "Draft",
			"review_status": "Draft",
		}
	)


def get_test_company():
	return frappe.db.get_single_value("Global Defaults", "default_company") or frappe.db.get_value(
		"Company", {}, "name"
	)


def get_test_customer():
	customer = frappe.db.get_value("Customer", {}, "name")
	if customer:
		return customer

	doc = frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": "VAT Process Test Customer",
			"customer_type": "Company",
			"customer_group": get_valid_default_customer_group(),
			"territory": get_valid_default_territory(),
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def get_test_supplier():
	supplier = frappe.db.get_value("Supplier", {}, "name")
	if supplier:
		return supplier

	doc = frappe.get_doc(
		{
			"doctype": "Supplier",
			"supplier_name": "VAT Process Test Supplier",
			"supplier_group": get_valid_default_supplier_group(),
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def get_test_terms_and_conditions():
	terms_name = "VAT Process Test Terms"
	if frappe.db.exists("Terms and Conditions", terms_name):
		doc = frappe.get_doc("Terms and Conditions", terms_name)
		if not doc.terms:
			doc.terms = "<p>VAT Process test terms</p>"
			if hasattr(doc, "buying"):
				doc.buying = 1
			doc.save(ignore_permissions=True)
		return doc

	doc = frappe.get_doc(
		{
			"doctype": "Terms and Conditions",
			"title": terms_name,
			"buying": 1,
			"terms": "<p>VAT Process test terms</p>",
		}
	)
	doc.insert(ignore_permissions=True)
	return doc
