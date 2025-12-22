# Copyright (c) 2025, Galaxy Labs and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from tms.utils.whatsapp_utils import normalize_phone


class Booking(Document):
    def after_insert(self):
        # send WhatsApp to admin (your number) after booking is created
        try:
            send_booking_whatsapp(self)
            self.db_set("whatsapp_sent", 1)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "Booking WhatsApp Send Failed")


def send_booking_whatsapp(doc: Document):
    # Your admin WhatsApp number (store without +)
    admin_number = "966572405550"

    # build message text
    msg = (
        f"🚌 *New Booking* ({doc.name})\n"
        f"Name: {doc.customer_name}\n"
        f"Phone: {doc.phone}\n"
        f"Email: {doc.email or '-'}\n"
        f"Pickup: {doc.pickup_location or '-'}\n"
        f"Dropoff: {doc.dropoff_location or '-'}\n"
        f"Travel Date: {doc.travel_date or '-'}\n"
        f"Vehicle: {doc.vehicle_type or '-'}\n"
        f"Passengers: {doc.passengers or 0}\n"
        f"Message: {doc.message or '-'}\n"
        f"Source: {doc.source or 'Transport Hub'}"
    )

    # normalize booking customer phone (optional)
    customer_phone = normalize_phone(doc.phone)

    # send message to ADMIN via WhatsApp Message DocType
    frappe.get_doc({
        "doctype": "WhatsApp Message",
        "type": "Outgoing",
        "message_type": "Manual",
        "to": admin_number,
        "content_type": "text",
        "message": msg,
        "reference_doctype": "Booking",
        "reference_name": doc.name,
    }).insert(ignore_permissions=True)

    # (Optional) also send an auto-reply to customer
    if customer_phone:
        frappe.get_doc({
            "doctype": "WhatsApp Message",
            "type": "Outgoing",
            "message_type": "Manual",
            "to": customer_phone,
            "content_type": "text",
            "message": f"Thanks {doc.customer_name}! We received your booking: {doc.name}",
            "reference_doctype": "Booking",
            "reference_name": doc.name,
        }).insert(ignore_permissions=True)
