# Copyright (c) 2026, Galaxy Labs and Contributors
# See license.txt

import unittest

from frappe.utils import flt

from tms.transport_management_system.doctype.trip_invoice.trip_invoice import calculate_item_amounts


class TestTripInvoiceCalculations(unittest.TestCase):
	def test_vat_included_km_trip_totals(self):
		item = {
			"qty": 400,
			"rate": 2,
			"vat_rate": 15,
			"vat_category": "Standard 15%",
		}

		result = calculate_item_amounts(item, "Included")

		self.assertEqual(flt(result["total_amount"], 2), 800)
		self.assertEqual(flt(result["amount"], 2), 695.65)
		self.assertEqual(flt(result["vat_amount"], 2), 104.35)

	def test_manual_vat_adds_tax_on_top_of_net(self):
		item = {
			"qty": 1,
			"rate": 200,
			"vat_rate": 15,
			"vat_category": "Standard 15%",
		}

		result = calculate_item_amounts(item, "Manual VAT")

		self.assertEqual(flt(result["amount"], 2), 200)
		self.assertEqual(flt(result["vat_amount"], 2), 30)
		self.assertEqual(flt(result["total_amount"], 2), 230)
