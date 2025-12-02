# apps/tms/tms/utils/whatsapp_utils.py

import frappe
from frappe.utils.file_manager import save_file
from frappe.utils import now_datetime
import traceback


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def normalize_phone(number: str | None) -> str:
    """Normalize phone by stripping spaces and hyphens."""
    if not number:
        return ""
    return number.replace(" ", "").replace("-", "").strip()


def get_or_create_contact(whatsapp_id: str, display_name: str | None = None):
    """
    Ensure WhatsApp Contact row exists.

    Uses your DocType:
        name: WhatsApp Contact
        autoname: field:whatsapp_id
    """
    whatsapp_id = normalize_phone(whatsapp_id)
    if not whatsapp_id:
        return None

    doctype = "WhatsApp Contact"

    if frappe.db.exists(doctype, whatsapp_id):
        doc = frappe.get_doc(doctype, whatsapp_id)
        if display_name and not doc.display_name:
            doc.display_name = display_name
            doc.save(ignore_permissions=True)
        return doc

    doc = frappe.get_doc({
        "doctype": doctype,
        "whatsapp_id": whatsapp_id,
        "display_name": display_name or whatsapp_id,
    })
    doc.insert(ignore_permissions=True)
    return doc


# ---------------------------------------------------------------------------
# Main: send Trip PDF via WhatsApp
# ---------------------------------------------------------------------------

@frappe.whitelist()
def send_trip_pdf_via_whatsapp(trip_name):
    """Generate (or reuse) Trip PDF and send it to driver via WhatsApp Message."""

    # 1) Load Trip + Driver
    trip = frappe.get_doc("Trip", trip_name)
    staff = frappe.get_doc("Staff", trip.driver)

    # Clean phone
    phone = normalize_phone(staff.mobile_no)
    if not phone:
        frappe.throw("Driver phone number is missing or invalid.")

    # Ensure WhatsApp Contact exists (for analysis / linking)
    get_or_create_contact(
        whatsapp_id=phone,
        display_name=getattr(staff, "full_name", None) or staff.name,
    )

    # 2) Ensure we have a PUBLIC PDF file attached to Trip
    existing_files = frappe.get_all(
        "File",
        filters={"attached_to_doctype": "Trip", "attached_to_name": trip_name},
        fields=["name", "file_url", "file_name", "is_private"],
        order_by="creation desc",
    )

    file_url = None
    file_name = None

    # Prefer an already-public file, otherwise create one
    for f in existing_files:
        if not f.get("is_private"):
            file_url = f["file_url"]
            file_name = f["file_name"]
            break

    if not file_url:
        # Generate PDF and save as PUBLIC File (is_private=0 so Meta can download)
        pdf_data = frappe.attach_print("Trip", trip_name, doc=trip)
        file_doc = save_file(
            fname=pdf_data["fname"],
            content=pdf_data["fcontent"],
            dt="Trip",
            dn=trip_name,
            folder="Home/Attachments",
            is_private=0,   # ✅ Make it public so WhatsApp can access it
        )
        file_url = file_doc.file_url        # e.g. /files/Trip-TRIP-0001.pdf
        file_name = file_doc.file_name

    caption = f"Trip {trip_name} PDF attached."

    # 3) Create WhatsApp Message as MANUAL DOCUMENT
    msg = frappe.get_doc({
        "doctype": "WhatsApp Message",
        "type": "Outgoing",
        "message_type": "Manual",        # ✅ allowed: Manual / Template
        "to": phone,
        "content_type": "document",      # ✅ tells before_insert to send as document
        "attach": file_url,              # relative path; before_insert will prefix site URL
        "message": caption,              # caption on the document
        "reference_doctype": "Trip",
        "reference_name": trip_name,
    })

    status = "Success"
    response_payload = ""

    try:
        # Triggers before_insert -> notify() -> send to WhatsApp API
        msg.insert(ignore_permissions=True)

        # If your controller sets msg.status, use it
        if msg.status:
            status = msg.status

    except Exception:
        status = "Failed"
        response_payload = traceback.format_exc()

    # 4) Log send result (your WhatsApp Send Log)
    if frappe.db.exists("DocType", "WhatsApp Send Log"):
        frappe.get_doc({
            "doctype": "WhatsApp Send Log",
            "reference_doctype": "Trip",
            "reference_name": trip.name,
            "to": phone,
            "message_type": "Document",      # just a label for reporting
            "status": status,
            "file_link": file_url,
            "response_json": response_payload,
            "sent_at": now_datetime(),
        }).insert(ignore_permissions=True)

    # 5) If failed → raise so user sees error
    if status.lower() != "success":
        frappe.throw("WhatsApp send failed. See WhatsApp Send Log / Error Log for details.")

    # 6) Mark Kashf as sent once success
    if hasattr(trip, "kashf_sent") and not trip.kashf_sent:
        trip.db_set("kashf_sent", 1)
        trip.add_comment("Info", f"Kashf PDF sent successfully at {now_datetime()}")

    return {"status": "Success", "to": phone, "file_url": file_url}


# import frappe
# from frappe.utils.file_manager import save_file
# from frappe.utils import now_datetime
# import traceback


# @frappe.whitelist()
# def send_trip_pdf_via_whatsapp(trip_name):
#     # 1) Load Trip + Driver
#     trip = frappe.get_doc("Trip", trip_name)
#     staff = frappe.get_doc("Staff", trip.driver)

#     # Clean phone
#     phone = (staff.mobile_no or "").replace(" ", "").replace("-", "").strip()
#     if not phone:
#         frappe.throw("Driver phone number is missing or invalid.")

#     # 2) Ensure we have a PUBLIC PDF file attached to Trip
#     existing_files = frappe.get_all(
#         "File",
#         filters={"attached_to_doctype": "Trip", "attached_to_name": trip_name},
#         fields=["name", "file_url", "file_name", "is_private"],
#         order_by="creation desc",
#     )

#     file_url = None
#     file_name = None

#     # Prefer an already-public file, otherwise create one
#     for f in existing_files:
#         if not f.get("is_private"):
#             file_url = f["file_url"]
#             file_name = f["file_name"]
#             break

#     if not file_url:
#         # Generate PDF and save as PUBLIC File (is_private=0)
#         pdf_data = frappe.attach_print("Trip", trip_name, doc=trip)
#         file_doc = save_file(
#             fname=pdf_data["fname"],
#             content=pdf_data["fcontent"],
#             dt="Trip",
#             dn=trip_name,
#             folder="Home/Attachments",
#             is_private=0,   # ✅ MAKE IT PUBLIC SO WHATSAPP CAN DOWNLOAD
#         )
#         file_url = file_doc.file_url        # e.g. /files/trip-0001.pdf
#         file_name = file_doc.file_name

#     # 3) Ensure WhatsApp Contact exists
#     if not frappe.db.exists("WhatsApp Contact", phone):
#         frappe.get_doc({
#             "doctype": "WhatsApp Contact",
#             "name": phone,
#             "whatsapp_id": phone,
#         }).insert(ignore_permissions=True)

#     caption = f"Trip {trip_name} PDF attached."

#     # 4) Create WhatsApp Message as MANUAL DOCUMENT
#     msg = frappe.get_doc({
#         "doctype": "WhatsApp Message",
#         "type": "Outgoing",
#         "message_type": "Manual",        # allowed: Manual / Template
#         "to": phone,
#         "content_type": "document",      # <- tells before_insert to send as document
#         "attach": file_url,              # <- public URL, your before_insert will prefix site URL
#         "message": caption,              # caption on the document
#         "reference_doctype": "Trip",
#         "reference_name": trip_name,
#     })

#     status = "Success"
#     response_payload = ""

#     try:
#         # Triggers before_insert -> notify() -> send to WhatsApp API
#         msg.insert(ignore_permissions=True)
#     except Exception:
#         status = "Failed"
#         response_payload = traceback.format_exc()

#     # 5) Log send result
#     frappe.get_doc({
#         "doctype": "WhatsApp Send Log",
#         "reference_doctype": "Trip",
#         "reference_name": trip.name,
#         "to": phone,
#         "message_type": "Document",      # label in your log only
#         "status": status,
#         "file_link": file_url,
#         "response_json": response_payload,
#         "sent_at": now_datetime(),
#     }).insert(ignore_permissions=True)

#     if status == "Failed":
#         frappe.throw("WhatsApp send failed. See log for details.")

#     return {"status": "Success", "to": phone, "file_url": file_url}

