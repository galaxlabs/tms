import frappe
from frappe.utils.file_manager import save_file
from tms.utils.whatsapp_sender import send_whatsapp_document

@frappe.whitelist()
def send_trip_pdf_to_driver(trip_name):
    trip = frappe.get_doc("Trip", trip_name)

    # Skip if already sent
    if trip.kashf_sent:
        return "Already sent"

    # Generate PDF
    pdf = frappe.get_print(
        doctype="Trip",
        name=trip.name,
        print_format="Trip",
        as_pdf=True
    )

    file_doc = save_file(
        fname=f"Trip-{trip.name}.pdf",
        content=pdf,
        dt="Trip",
        dn=trip.name,
        is_private=1
    )

    # Send to WhatsApp
    result = send_whatsapp_document(
        to=trip.mobile_no,
        file_url=file_doc.file_url,
        caption=f"📄 Trip {trip.name} summary is ready for you."
    )

    # Mark as sent
    trip.db_set("kashf_sent", 1)

    # Optional: Log send status
    frappe.get_doc({
        "doctype": "WhatsApp Send Log",
        "reference_doctype": "Trip",
        "reference_name": trip.name,
        "to": trip.mobile_no,
        "message_type": "Document",
        "file_link": file_doc.file_url,
        "status": "Success" if result else "Failed",
    }).insert(ignore_permissions=True)

    return True
