# Copyright (c) 2025, Galaxy Labs and contributors
# For license information, please see license.txt

# Copyright (c) 2017, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt
# /home/xg/xg-b/apps/tms/tms/hotels/doctype/hotel_room/hotel_room.py

import frappe
from frappe.model.document import Document


class HotelRoom(Document):
	def validate(self):
		if not self.capacity:
			self.capacity, self.extra_bed_capacity = frappe.db.get_value('Hotel Room Type',
					self.hotel_room_type, ['capacity', 'extra_bed_capacity'])
