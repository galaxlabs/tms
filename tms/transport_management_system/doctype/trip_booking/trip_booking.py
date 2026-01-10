# Copyright (c) 2026, Galaxy Labs and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import get_datetime


class TripBooking(Document):
    def validate(self):
        # 1) passenger_count = number of rows in booking_passenger (always synced)
        row_count = len(self.get("booking_passenger") or [])
        if (self.passenger_count or 0) != row_count:
            self.passenger_count = row_count

        # 2) departure_at = departure_date + departure_time
        self.departure_at = None
        if self.departure_date and self.departure_time:
            try:
                self.departure_at = get_datetime(f"{self.departure_date} {self.departure_time}")
            except Exception:
                self.departure_at = None

        # 3) defaults
        if not self.status:
            self.status = "DRAFT"

        if not self.booking_source:
            self.booking_source = "WHATSAPP"


# import frappe
# from frappe.model.document import Document
# from frappe.utils import get_datetime, now_datetime


# class TripBooking(Document):
#     def validate(self):
#         # 1) passenger_count = number of rows in booking_passenger
#         self.passenger_count = len(self.get("booking_passenger") or [])

#         # 2) departure_at = departure_date + departure_time
#         self.departure_at = None
#         if self.departure_date and self.departure_time:
#             # departure_time might be 'HH:MM:SS' or a Time object
#             dt_str = f"{self.departure_date} {self.departure_time}"
#             try:
#                 self.departure_at = get_datetime(dt_str)
#             except Exception:
#                 # Never crash booking save due to parsing edge cases
#                 self.departure_at = None

#         # Optional: default status
#         if not self.status:
#             self.status = "DRAFT"

#         # Optional: default source
#         if not self.booking_source:
#             self.booking_source = "WHATSAPP"
