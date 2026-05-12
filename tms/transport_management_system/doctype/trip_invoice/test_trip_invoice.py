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
