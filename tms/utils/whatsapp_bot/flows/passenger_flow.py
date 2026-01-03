# apps/tms/tms/utils/whatsapp_bot/flows/passenger_flow.py
from tms.utils.whatsapp_bot.helpers.json_store import get_json
import frappe


def write_passengers_and_finalize(trip, contact, lang):
    """
    Prefer passengers stored on contact.received_files_json["passengers"].
    Avoid duplicates.
    Returns count added.
    """
    if trip.get("passengers"):
        return 0  # avoid duplicates

    state = get_json(contact, "received_files_json", {}) or {}
    passengers = state.get("passengers") or []

    added = 0
    for p in passengers:
        name = (p.get("full_name") or p.get("passenger_name") or "").strip()
        id_no = (p.get("id_no") or p.get("idpassport_no") or "").strip()
        nat = (p.get("nationality") or "").strip()

        if not name or not id_no:
            continue

        row = trip.append("passengers", {})
        row.passenger_name = name
        row.idpassport_no = id_no
        row.nationality = nat
        added += 1

    if added:
        trip.save(ignore_permissions=True)

    return added
