# /home/xg/xg-b/apps/tms/tms/utils/whatsapp_bot/flows/trip_flow.py

import json
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

        state = (getattr(contact, "bot_state", "") or "").upper()
        if state != "DONE":
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

        # Prepare contact updates (single UPDATE, no .save())
        updates = {}

        if hasattr(contact, "current_trip"):
            updates["current_trip"] = trip.name
            contact.current_trip = trip.name

        if hasattr(contact, "bot_state"):
            updates["bot_state"] = "WAITING_PASSENGER_COUNT"
            contact.bot_state = "WAITING_PASSENGER_COUNT"

        if hasattr(contact, "expected_passengers"):
            updates["expected_passengers"] = 0
            contact.expected_passengers = 0

        if hasattr(contact, "received_images"):
            updates["received_images"] = 0
            contact.received_images = 0

        if hasattr(contact, "collected_file_urls_json"):
            updates["collected_file_urls_json"] = "[]"
            contact.collected_file_urls_json = "[]"

        if hasattr(contact, "resend_indexes_json"):
            updates["resend_indexes_json"] = "[]"
            contact.resend_indexes_json = "[]"

        if hasattr(contact, "resend_ptr"):
            updates["resend_ptr"] = 0
            contact.resend_ptr = 0

        # This is the critical change:
        if updates:
            frappe.db.set_value(contact.doctype, contact.name, updates, update_modified=False)

    return trip
