# Copyright (c) 2025, Galaxy Labs and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from tms.utils.party_defaults import get_valid_default_customer_group, get_valid_default_territory


class TestStaff(FrappeTestCase):
	pass

	def test_staff_uses_non_group_customer_defaults(self):
		frappe.db.set_single_value("Selling Settings", "customer_group", "All Customer Groups")
		frappe.db.set_single_value("Selling Settings", "territory", "All Territories")

		doc = frappe.new_doc("Staff")
		doc.first_name = "Default"
		doc.last_name = "Customer"
		doc.full_name = "Default Customer"
		doc.email = "default.customer@example.com"

		self.assertEqual(doc.get_default_customer_group(), get_valid_default_customer_group())
		self.assertEqual(doc.get_default_territory(), get_valid_default_territory())
		self.assertFalse(frappe.db.get_value("Customer Group", doc.get_default_customer_group(), "is_group"))
		self.assertFalse(frappe.db.get_value("Territory", doc.get_default_territory(), "is_group"))
