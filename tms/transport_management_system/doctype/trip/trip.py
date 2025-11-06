# Copyright (c) 2025, Galaxy Labs and contributors
# For license information, please see license.txt

import frappe
import uuid
import qrcode
import base64
from io import BytesIO
from frappe.website.website_generator import WebsiteGenerator
from frappe.utils import getdate, get_url
from hijri_converter import Gregorian

class Trip(WebsiteGenerator):
    def before_insert(self):
        # UUID
        if not self.uuid:
            self.uuid = str(uuid.uuid4())

        # Use UUID as public route
        if not self.route:
            self.route = self.uuid

        # Hijri date
        if self.date and not self.hijri_date:
            g = getdate(self.date)
            h = Gregorian(g.year, g.month, g.day).to_hijri()
            self.hijri_date = f"{h.year:04d}-{h.month:02d}-{h.day:02d}"

    def after_insert(self):
        # Build public URL from site config (respects https and domain)
        if self.route and not self.qr_code:
            base_url = get_url()                 # e.g. https://yourdomain.com
            public_url = f"{base_url.rstrip('/')}/{self.route.lstrip('/')}"
            self.qr_code = self.generate_qr_code(public_url)
            self.db_set("qr_code", self.qr_code)

    def generate_qr_code(self, data: str) -> str:
        qr = qrcode.QRCode(version=1, box_size=10, border=2)
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image()
        buf = BytesIO()
        img.save(buf, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()




# @frappe.whitelist()
# def create_connected_trip(source_trip, route_name, connection_type=None):
#     source_doc = frappe.get_doc("Trip", source_trip)
#     new_trip = frappe.new_doc("Trip")
#     new_trip.driver = source_doc.driver
#     new_trip.assigned_vehicle = source_doc.assigned_vehicle
#     new_trip.date = frappe.utils.nowdate()
#     new_trip.from_route = frappe.get_doc("Route", route_name).from_city  # corrected name
#     new_trip.to = frappe.get_doc("Route", route_name).to_city     # corrected name

#     new_trip.insert(ignore_permissions=True)
#     return new_trip.name

