import frappe
from datetime import timedelta
from frappe.utils import nowdate, now_datetime


def get_or_create_trip(driver_name: str, contact):
    """
    Returns a Trip doc for this contact.
    Reuse current_trip if still valid.
    Otherwise create a new Trip and attach to contact.
    """
    trip = None
    current_trip_name = getattr(contact, "current_trip", None)

    # Try reuse
    if current_trip_name and frappe.db.exists("Trip", current_trip_name):
        t = frappe.get_doc("Trip", current_trip_name)

        # If DONE, don't reuse
        state = (getattr(contact, "bot_state", "") or "").upper()
        if state != "DONE":
            # Keep reuse only if recent and scheduled/departed
            created_ok = True
            try:
                created_ok = (now_datetime() - t.creation) <= timedelta(hours=12)
            except Exception:
                created_ok = True

            if t.trip_status in ("Scheduled", "Departed") and created_ok:
                trip = t

    # Create new trip
    if not trip:
        trip = frappe.new_doc("Trip")
        trip.driver = driver_name
        trip.trip_status = "Scheduled"
        trip.date = nowdate()
        trip.departure = now_datetime()
        trip.insert(ignore_permissions=True)

        # Attach to contact
        if hasattr(contact, "current_trip"):
            contact.current_trip = trip.name
        if hasattr(contact, "bot_state"):
            contact.bot_state = "WAITING_PASSENGER_COUNT"
        if hasattr(contact, "expected_passengers"):
            contact.expected_passengers = 0
        if hasattr(contact, "received_images"):
            contact.received_images = 0
        if hasattr(contact, "collected_file_urls_json"):
            contact.collected_file_urls_json = "[]"
        if hasattr(contact, "resend_indexes_json"):
            contact.resend_indexes_json = "[]"
        if hasattr(contact, "resend_ptr"):
            contact.resend_ptr = 0

        contact.save(ignore_permissions=True)

    return trip
