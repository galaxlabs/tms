from unittest.mock import patch

from frappe.tests.utils import FrappeTestCase

from tms.utils import get_notifications_map, trigger_whatsapp_notifications


class TestWhatsAppNotificationGuard(FrappeTestCase):
	def test_get_notifications_map_returns_empty_when_doctype_table_missing(self):
		with patch("frappe.db.table_exists", return_value=False):
			self.assertEqual(get_notifications_map(), {})

	def test_trigger_whatsapp_notifications_returns_when_doctype_table_missing(self):
		with patch("frappe.db.table_exists", return_value=False):
			self.assertIsNone(trigger_whatsapp_notifications("Daily"))
