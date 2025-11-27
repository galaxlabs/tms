# tms/transport_management_system/whatsapp_bot.py

import frappe
import requests

from frappe.utils import (
    nowdate,
    now_datetime,
    getdate,
    get_datetime,
)
from frappe.utils.file_manager import save_file

from tms.utils.vision import extract_passenger_from_image  # you implement this


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

def normalize_phone(raw):
    """Normalize WhatsApp phone number and Staff.mobile_no to same format."""
    if not raw:
        return raw
    return raw.replace(" ", "").replace("+", "")


def is_trip_active(trip, max_hours=12):
    """
    Decide if a Trip is still 'active' and should be reused.

    Rules:
    - trip_status != 'Cancelled'
    - arrival is empty
    - date >= today
    - created within last `max_hours`
    """
    # Cancelled → not active
    if trip.trip_status == "Cancelled":
        return False

    # Arrival set → treated as finished
    if trip.arrival:
        return False

    # Older than today → treat as closed
    if getdate(trip.date) < getdate(nowdate()):
        return False

    # If too old (safety), e.g. > 12 hours
    hours_since_creation = (
        now_datetime() - get_datetime(trip.creation)
    ).total_seconds() / 3600.0

    if hours_since_creation > max_hours:
        return False

    return True


def get_or_create_trip_for_driver(driver_name, mobile_no):
    """
    1) Fetch latest Trip for this driver.
    2) If active → reuse.
    3) Otherwise → create a new Trip and return it.
    """

    latest_trip_name = frappe.db.get_value(
        "Trip",
        {"driver": driver_name},
        "name",
        order_by="creation desc",
    )

    if latest_trip_name:
        trip = frappe.get_doc("Trip", latest_trip_name)
        if is_trip_active(trip):
            return trip

    # No active trip → create fresh one
    trip = frappe.new_doc("Trip")
    trip.driver = driver_name
    trip.mobile_no = mobile_no
    trip.date = nowdate()
    trip.trip_status = "Scheduled"  # matches your options: Scheduled/Departed/Arrived/Cancelled
    # You can set any defaults (trip_route, etc.) here if needed

    trip.insert(ignore_permissions=True)
    frappe.db.commit()

    frappe.logger().info(
        f"[TMS WA] Created new Trip {trip.name} for driver {driver_name}"
    )
    return trip


def attach_whatsapp_media_to_trip(wa_doc, trip):
    """
    Download WhatsApp image and attach it to Trip.

    NOTE:
    - Adjust `media_url` / `media_id` field names to match the official
      WhatsApp Message DocType in the Frappe app you installed.
    - For production, replace raw `requests.get` with the app's own media helper
      if it provides one.
    """

    media_url = getattr(wa_doc, "media_url", None)
    media_id = getattr(wa_doc, "media_id", None)

    if not (media_url or media_id):
        frappe.logger().info(f"[TMS WA] No media on message {wa_doc.name}")
        return None

    # Example: use media_url directly. If your app uses media_id + separate endpoint,
    # implement that here instead.
    try:
        resp = requests.get(media_url, timeout=20)
        resp.raise_for_status()
    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            "[TMS WA] Failed to download WhatsApp media",
        )
        return None

    filename = f"Trip-{trip.name}-{wa_doc.name}.jpg"

    file_doc = save_file(
        filename=filename,
        content=resp.content,
        dt="Trip",
        dn=trip.name,
        is_private=1,
    )

    return file_doc


# -------------------------------------------------------------------
# Main entrypoint called from hooks
# -------------------------------------------------------------------

def process_whatsapp_message(doc, event=None):
    """
    Called on after_insert of WhatsApp Message.

    Flow:

    1) Only handle image messages.
    2) Find driver (Staff) based on WhatsApp sender number.
    3) Get or create Trip for that driver.
       - If latest Trip is active → reuse.
       - Else → create new Trip.
    4) Download and attach WhatsApp image to Trip.
    5) Use OCR/AI to extract passenger details from the image.
    6) Append a row to Trip.passengers child table.
    """

    # 1) Only handle image messages
    # Adjust this condition to match the official app's field names & values.
    # Example: doc.message_type could be "Image".
    if getattr(doc, "message_type", None) != "Image":
        return

    sender_no = normalize_phone(doc.sender)

    # 2) Find driver from Staff.mobile_no
    driver_name = frappe.db.get_value(
        "Staff",
        {"mobile_no": sender_no},
        "name",
    )

    if not driver_name:
        frappe.logger().info(
            f"[TMS WA] No Staff/driver found for WhatsApp number: {sender_no}"
        )
        return

    # 3) Get or create Trip
    trip = get_or_create_trip_for_driver(driver_name, sender_no)

    # 4) Attach WhatsApp image to Trip
    file_doc = attach_whatsapp_media_to_trip(doc, trip)
    if not file_doc:
        frappe.logger().info(
            f"[TMS WA] Could not attach media for WhatsApp message {doc.name}"
        )
        return

    # 5) Extract passenger info from image (OCR/AI)
    passenger = extract_passenger_from_image(file_doc)
    if not passenger:
        frappe.logger().info(
            f"[TMS WA] No passenger data extracted from image {file_doc.name}"
        )
        return

    # 6) Append row to passengers child table (Passengers istable DocType)
    row = trip.append("passengers", {})
    row.passenger_name = passenger.get("passenger_name")
    row.idpassport_no = passenger.get("idpassport_no")
    row.nationality = passenger.get("nationality")
    row.contact_no = passenger.get("contact_no") or sender_no
    # Attach field expects file_url
    row.documents = file_doc.file_url
    row.ocr_confidence = passenger.get("ocr_confidence") or 0

    trip.flags.ignore_permissions = True
    trip.save()
    frappe.db.commit()

    frappe.logger().info(
        f"[TMS WA] Added passenger row in Trip {trip.name} from WhatsApp message {doc.name}"
    )
