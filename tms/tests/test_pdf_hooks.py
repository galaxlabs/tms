import frappe
from frappe.tests.utils import FrappeTestCase


class TestPdfHooks(FrappeTestCase):
	def test_submit_pdf_hook_target_is_resolvable(self):
		hook = frappe.get_attr("tms.utils.pdf_hooks.create_pdf_on_submit")
		self.assertTrue(callable(hook))
