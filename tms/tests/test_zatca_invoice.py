import base64
from unittest.mock import MagicMock
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from tms.utils import zatca_invoice


class TestZatcaInvoice(FrappeTestCase):
    def test_get_company_invoice_print_format_falls_back_when_column_missing(self):
        with patch(
            "tms.utils.zatca_invoice._doctype_field_is_queryable",
            return_value=False,
        ), patch("tms.utils.zatca_invoice.frappe.db.get_value") as get_value:
            self.assertEqual(
                zatca_invoice.get_company_invoice_print_format("Test Company"),
                zatca_invoice.DEFAULT_SALES_INVOICE_PRINT_FORMAT,
            )

        get_value.assert_not_called()

    def test_get_company_invoice_print_format_prefers_company_setting(self):
        with patch(
            "tms.utils.zatca_invoice._doctype_field_is_queryable",
            return_value=True,
        ), patch(
            "tms.utils.zatca_invoice.frappe.db.get_value",
            return_value="CELTC LTR Sales Invoice",
        ):
            self.assertEqual(
                zatca_invoice.get_company_invoice_print_format("Test Company"),
                "CELTC LTR Sales Invoice",
            )

    def test_get_company_invoice_print_format_falls_back_to_default(self):
        with patch(
            "tms.utils.zatca_invoice._doctype_field_is_queryable",
            return_value=True,
        ), patch("tms.utils.zatca_invoice.frappe.db.get_value", return_value=None):
            self.assertEqual(
                zatca_invoice.get_company_invoice_print_format("Test Company"),
                zatca_invoice.DEFAULT_SALES_INVOICE_PRINT_FORMAT,
            )

    def test_ensure_public_invoice_qr_builds_tlv_payload_not_public_url(self):
        doc = SimpleNamespace(
            name="ACC-SINV-2026-0001",
            company="Test Company",
            zatca_qr_png=None,
            zatca_qr_payload=None,
            company_tax_id="312345678900003",
            posting_date="2026-04-28",
            posting_time="10:11:12",
            grand_total=575,
            total_taxes_and_charges=75,
        )
        company_doc = SimpleNamespace(
            company_name="Test Company",
            company_name_arabic="شركة الاختبار",
            tax_id="312345678900003",
        )

        with patch(
            "tms.utils.zatca_invoice.frappe.get_doc",
            return_value=company_doc,
        ):
            zatca_invoice.ensure_public_invoice_qr(doc)

        self.assertFalse("api/method" in doc.zatca_qr_payload)
        self.assertTrue(isinstance(doc.zatca_qr_payload, str))
        self.assertGreater(len(doc.zatca_qr_payload), 10)

    def test_build_zatca_qr_payload_uses_company_arabic_name_first(self):
        doc = SimpleNamespace(
            company="Test Company",
            company_tax_id="312345678900003",
            posting_date="2026-04-28",
            posting_time="10:11:12",
            grand_total=575,
            total_taxes_and_charges=75,
        )
        company_doc = SimpleNamespace(
            company_name="Test Company",
            company_name_arabic="شركة الاختبار",
            tax_id="312345678900003",
        )

        with patch("tms.utils.zatca_invoice.frappe.get_doc", return_value=company_doc):
            payload = zatca_invoice.build_zatca_qr_payload(doc)

        self.assertEqual(
            base64.b64decode(payload).decode("utf-8"),
            "\x01\x19شركة الاختبار\x02\x0f312345678900003\x03\x132026-04-28T10:11:12\x04\x06575.00\x05\x0575.00",
        )

    def test_sync_sales_invoice_qr_payload_rewrites_legacy_payload(self):
        doc = SimpleNamespace(
            name="ACC-SINV-2026-00002",
            zatca_qr_payload="https://legacy.example/printview",
            db_set=MagicMock(),
        )

        with patch(
            "tms.utils.zatca_invoice.build_zatca_qr_payload",
            return_value="new-tlv-payload",
        ):
            result = zatca_invoice.sync_sales_invoice_qr_payload(doc)

        self.assertEqual(result, "new-tlv-payload")
        self.assertEqual(doc.zatca_qr_payload, "new-tlv-payload")
        doc.db_set.assert_called_once_with("zatca_qr_payload", "new-tlv-payload", update_modified=False)

    def test_validate_public_invoice_access_requires_permission_even_with_token(self):
        doc = SimpleNamespace(
            zatca_qr_png="valid-token",
            has_permission=lambda permission: False,
        )

        with patch("tms.utils.zatca_invoice.frappe.session", SimpleNamespace(user="Administrator")):
            with self.assertRaises(frappe.PermissionError):
                zatca_invoice.validate_public_invoice_access(doc, token="valid-token")
