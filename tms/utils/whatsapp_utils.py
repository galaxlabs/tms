import frappe
from frappe.utils import now_datetime


def can_send_session_message(phone: str) -> bool:
    phone = normalize_phone(phone)
    contact_name = frappe.db.get_value("WhatsApp Contact", {"phone": phone}, "name")
    if not contact_name:
        return False  # unknown contact -> safest: require template

    contact = frappe.get_doc("WhatsApp Contact", contact_name)

    # Prefer expires field if you add it
    expires = getattr(contact, "conversation_expires_at", None)
    if expires:
        return now_datetime() <= expires

    last_in = getattr(contact, "last_inbound_at", None)
    if not last_in:
        return False
    # If you didn't store expires, you can compute it:
    return (now_datetime() - last_in).total_seconds() <= 24 * 3600

# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def normalize_phone(number: str | None) -> str:
    if not number:
        return ""
    n = str(number).strip().replace(" ", "").replace("-", "")
    if n.startswith("00"):
        n = n[2:]
    if n.startswith("+"):
        n = n[1:]
    return n


def _staff_by_phone(raw_phone: str):
    """
    Find Staff row whose mobile_no matches this phone (with a few variants).
    """
    phone = normalize_phone(raw_phone)
    if not phone:
        return None

    candidates = {phone}
    if phone.startswith("+"):
        candidates.add(phone[1:])
    if phone.startswith("00"):
        candidates.add(phone[2:])

    staff = frappe.db.get_value(
        "Staff",
        {"mobile_no": ["in", list(candidates)]},
        ["name", "full_name", "first_name"],
        as_dict=True,
    )
    return staff


def get_or_create_contact(whatsapp_id: str, display_name: str | None = None):
    """
    Ensure WhatsApp Contact row exists.

    Uses your DocType:
        name: WhatsApp Contact
        autoname: field:whatsapp_id

    Extra:
    - If a Staff with this mobile_no exists, link it and
      prefer Staff.full_name / first_name as display_name.
    """
    whatsapp_id = normalize_phone(whatsapp_id)
    if not whatsapp_id:
        return None

    doctype = "WhatsApp Contact"

    # Try to resolve Staff
    staff = _staff_by_phone(whatsapp_id)

    staff_name = staff["name"] if staff else None
    staff_display = (
        (staff.get("full_name") or staff.get("first_name"))
        if staff
        else None
    )

    # Prefer Staff name over profile name
    final_display_name = staff_display or display_name or whatsapp_id

    # Existing contact?
    if frappe.db.exists(doctype, whatsapp_id):
        doc = frappe.get_doc(doctype, whatsapp_id)

        dirty = False
        if final_display_name and not doc.display_name:
            doc.display_name = final_display_name
            dirty = True

        # if you added a "staff" Link field on WhatsApp Contact
        if staff_name and getattr(doc, "staff", None) != staff_name:
            doc.staff = staff_name
            dirty = True

        if dirty:
            doc.save(ignore_permissions=True)

        return doc

    # New contact
    data = {
        "doctype": doctype,
        "whatsapp_id": whatsapp_id,
        "display_name": final_display_name,
    }
    if staff_name:
        data["staff"] = staff_name

    doc = frappe.get_doc(data)
    doc.insert(ignore_permissions=True)
    return doc


# ---------------------------------------------------------------------------
# Main: send Trip PDF via WhatsApp
# ---------------------------------------------------------------------------

@frappe.whitelist()
def send_trip_pdf_via_whatsapp(trip_name: str):
    """Compatibility wrapper for the shared WhatsApp PDF sender."""
    from tms.utils.whatsapp_document import send_trip_pdf_via_whatsapp as send_trip_pdf

    return send_trip_pdf(trip_name)

# import frappe
# from frappe.utils.file_manager import save_file
# from frappe.utils import now_datetime
# from tms.utils.chrome_pdf import get_pdf as chrome_get_pdf
# import traceback
# import re


# # ---------------------------------------------------------------------------
# # Small helpers
# # ---------------------------------------------------------------------------

# def normalize_phone(number: str | None) -> str:
#     """Normalize phone by stripping spaces and hyphens."""
#     if not number:
#         return ""
#     return number.replace(" ", "").replace("-", "").strip()


# def _staff_by_phone(raw_phone: str):
#     """
#     Find Staff row whose mobile_no matches this phone (with a few variants).
#     """
#     phone = normalize_phone(raw_phone)
#     if not phone:
#         return None

#     candidates = {phone}
#     if phone.startswith("+"):
#         candidates.add(phone[1:])
#     if phone.startswith("00"):
#         candidates.add(phone[2:])

#     staff = frappe.db.get_value(
#         "Staff",
#         {"mobile_no": ["in", list(candidates)]},
#         ["name", "full_name", "first_name"],
#         as_dict=True,
#     )
#     return staff


# def get_or_create_contact(whatsapp_id: str, display_name: str | None = None):
#     """
#     Ensure WhatsApp Contact row exists.

#     Uses your DocType:
#         name: WhatsApp Contact
#         autoname: field:whatsapp_id

#     Extra:
#     - If a Staff with this mobile_no exists, link it and
#       prefer Staff.full_name / first_name as display_name.
#     """
#     whatsapp_id = normalize_phone(whatsapp_id)
#     if not whatsapp_id:
#         return None

#     doctype = "WhatsApp Contact"

#     # Try to resolve Staff
#     staff = _staff_by_phone(whatsapp_id)

#     staff_name = staff["name"] if staff else None
#     staff_display = (
#         (staff.get("full_name") or staff.get("first_name"))
#         if staff
#         else None
#     )

#     # Prefer Staff name over profile name
#     final_display_name = staff_display or display_name or whatsapp_id

#     # Existing contact?
#     if frappe.db.exists(doctype, whatsapp_id):
#         doc = frappe.get_doc(doctype, whatsapp_id)

#         dirty = False
#         if final_display_name and not doc.display_name:
#             doc.display_name = final_display_name
#             dirty = True

#         # if you added a "staff" Link field on WhatsApp Contact
#         if staff_name and getattr(doc, "staff", None) != staff_name:
#             doc.staff = staff_name
#             dirty = True

#         if dirty:
#             doc.save(ignore_permissions=True)

#         return doc

#     # New contact
#     data = {
#         "doctype": doctype,
#         "whatsapp_id": whatsapp_id,
#         "display_name": final_display_name,
#     }
#     if staff_name:
#         data["staff"] = staff_name

#     doc = frappe.get_doc(data)
#     doc.insert(ignore_permissions=True)
#     return doc


# # ---------------------------------------------------------------------------
# # Main: send Trip PDF via WhatsApp
# # ---------------------------------------------------------------------------

# @frappe.whitelist()
# def send_trip_pdf_via_whatsapp(trip_name: str):
#     """Generate (or reuse) Trip PDF and send it to driver via WhatsApp Message."""

#     # 1) Load Trip + Driver
#     trip = frappe.get_doc("Trip", trip_name)
#     staff = frappe.get_doc("Staff", trip.driver)

#     # Clean phone
#     phone = normalize_phone(staff.mobile_no)
#     if not phone:
#         frappe.throw("Driver phone number is missing or invalid.")

#     # Ensure WhatsApp Contact exists (for analysis / linking)
#     get_or_create_contact(
#         whatsapp_id=phone,
#         display_name=getattr(staff, "full_name", None) or staff.name,
#     )

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
#         # ✅ Generate HTML using Frappe and PDF using Chrome-based generator
#         print_format = None  # e.g. "Trip Kashf" if you have a specific format
#         html = frappe.get_print(
#             "Trip",
#             trip_name,
#             print_format=print_format,
#             doc=trip,
#             no_letterhead=0,
#         )

#         # Options similar to wkhtml; use what your chrome_pdf expects
#         pdf_content = chrome_get_pdf(html, options={"page-size": "A4"})

#         fname = f"Trip-{trip_name}.pdf"

#         file_doc = save_file(
#             fname=fname,
#             content=pdf_content,
#             dt="Trip",
#             dn=trip_name,
#             folder="Home/Attachments",
#             is_private=0,   # public so WhatsApp / Meta can access it
#         )
#         file_url = file_doc.file_url        # e.g. /files/Trip-TRIP-0001.pdf
#         file_name = file_doc.file_name

#     caption = f"Trip {trip_name} PDF attached."

#     # 3) Create WhatsApp Message as MANUAL DOCUMENT
#     msg = frappe.get_doc({
#         "doctype": "WhatsApp Message",
#         "type": "Outgoing",
#         "message_type": "Manual",        # Manual / Template
#         "to": phone,
#         "content_type": "document",      # tells before_insert to send as document
#         "attach": file_url,              # relative path; before_insert will prefix site URL
#         "message": caption,              # caption on the document
#         "reference_doctype": "Trip",
#         "reference_name": trip_name,
#     })

#     status = "Success"
#     response_payload = ""

#     try:
#         # Triggers before_insert -> notify() -> send to WhatsApp API
#         msg.insert(ignore_permissions=True)

#         if msg.status:
#             status = msg.status

#     except Exception:
#         status = "Failed"
#         response_payload = traceback.format_exc()

#     # 4) Log send result (WhatsApp Send Log)
#     if frappe.db.exists("DocType", "WhatsApp Send Log"):
#         frappe.get_doc({
#             "doctype": "WhatsApp Send Log",
#             "reference_doctype": "Trip",
#             "reference_name": trip.name,
#             "to": phone,
#             "message_type": "Document",      # just a label for reporting
#             "status": status,
#             "file_link": file_url,
#             "response_json": response_payload,
#             "sent_at": now_datetime(),
#         }).insert(ignore_permissions=True)

#     # 5) If failed → raise so user sees error
#     if status.lower() != "success":
#         frappe.throw("WhatsApp send failed. See WhatsApp Send Log / Error Log for details.")

#     # 6) Mark Kashf as sent once success
#     if hasattr(trip, "kashf_sent") and not trip.kashf_sent:
#         trip.db_set("kashf_sent", 1)
#         trip.add_comment("Info", f"Kashf PDF sent successfully at {now_datetime()}")

#     return {"status": "Success", "to": phone, "file_url": file_url}
