import frappe

from tms.utils.whatsapp_document import send_trip_pdf_via_whatsapp

@frappe.whitelist()
def send_trip_pdf_to_driver(trip_name):
    return send_trip_pdf_via_whatsapp(trip_name)
