# Copyright (c) 2025, Galaxy Labs and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import date_diff, add_days

class RentalContract(Document):
    def validate(self):
        self.calculate_total_rent()

    def calculate_total_rent(self):
        if not self.from_date or not self.to_date or not self.billing_period:
            return

        days = date_diff(self.to_date, self.from_date)

        if self.billing_period == "Monthly":
            months = max(1, days // 30)
            self.total_rent = self.monthly_rent * months

        elif self.billing_period == "Weekly":
            weeks = max(1, days // 7)
            self.total_rent = (self.monthly_rent / 4.0) * weeks

        elif self.billing_period == "Yearly":
            years = max(1, days // 365)
            self.total_rent = self.monthly_rent * 12 * years


# class RentalContract(Document):
#     def validate(self):
#         self.validate_room_availability()
#         self.calculate_total_rent()

#     def validate_room_availability(self):
#         overlaps = frappe.db.sql("""
#             SELECT name FROM `tabRental Contract`
#             WHERE room=%s AND docstatus < 2
#               AND (from_date BETWEEN %s AND %s OR to_date BETWEEN %s AND %s)
#               AND name != %s
#         """, (self.room, self.from_date, self.to_date, self.from_date, self.to_date, self.name))

#         if overlaps:
#             frappe.throw("Room already booked in this date range.")

#     def calculate_total_rent(self):
#         months = (self.to_date.year - self.from_date.year) * 12 + (self.to_date.month - self.from_date.month) + 1
#         self.total_rent = months * self.monthly_rent


