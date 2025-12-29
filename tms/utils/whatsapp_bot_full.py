# tms/tms/utils/whatsapp_bot_full.py
from __future__ import annotations

import json
import re
import frappe
from frappe.utils import now_datetime

# You already have these utilities in your project (from your earlier code snippet)
from tms.utils.whatsapp_utils import (
    normalize_phone,
    get_or_create_contact,
)

# This is the batch OCR + upsert + confidence gate service we created earlier
from tms.utils.passenger_ocr_service import process_passenger_images_for_trip


# -----------------------------
# Session / State helpers
# -----------------------------
STATE_IDLE = "IDLE"
STATE_ASK_PASSENGER_COUNT = "ASK_PASSENGER_COUNT"
STATE_COLLECTING_DOCS = "COLLECTING_DOCS"
STATE_RESEND_DOCS = "RESEND_DOCS"
STATE_ASK_ROUTE = "ASK_ROUTE"
STATE_DONE = "DONE"

SITE_NAME = "tms-erp.online"

CONF_THRESHOLD = 0.80  # informational (actual gate is inside service)


def _jload(s: str) -> list:
    if not s:
        return []
    try:
        return json.loads(s)
    except Exception:
        return []


def _jdump(v: list) -> str:
    return json.dumps(v or [], ensure_ascii=False)


def _parse_int(text: str) -> int | None:
    if not text:
        return None
    m = re.search(r"\d+", text)
    return int(m.group()) if m else None


def _parse_route_text(text: str) -> tuple[str | None, str | None]:
    """
    Accepts:
      "Jeddah Makkah"
      "From Jeddah to Makkah"
      "Jeddah -> Makkah"
    Returns (from_city, to_city) or (None, None)
    """
    if not text:
        return None, None

    t = text.strip().replace("→", "->")
    t = re.sub(r"\s+", " ", t)

    # common forms: "from X to Y"
    m = re.search(r"from\s+(.+?)\s+to\s+(.+)$", t, re.I)
    if m:
        return m.group(1).strip(), m.group(2).strip()

    # arrow form
    if "->" in t:
        parts = [p.strip() for p in t.split("->", 1)]
        if len(parts) == 2:
            return parts[0], parts[1]

    # two words/groups
    parts = t.split(" ")
    if len(parts) >= 2:
        # assume first token(s) is from, last token(s) is to
        # simplest: first word as from, last word as to
        return parts[0].strip(), parts[-1].strip()

    return None, None


# -----------------------------
# Messaging helpers
# -----------------------------
def _send_reply(waba_message_doc, text: str):
    """
    Replace this with your existing WhatsApp reply sender.
    You likely already have something like `send_text_via_whatsapp(...)`.
    """
    # Example placeholder: log only
    frappe.logger().info(f"[WA Reply] to={waba_message_doc.from_number} text={text}")


# -----------------------------
# Staff auth
# -----------------------------
def _is_staff_phone(phone_e164: str) -> bool:
    """
    Adjust this to your real staff check.
    You said: check sender no as register in staff
    """
    # Example: a "Staff" doctype having phone field
    return bool(frappe.db.exists("Staff", {"phone": phone_e164}))


# -----------------------------
# Trip / Route (plug your existing logic)
# -----------------------------
def _get_or_create_trip_for_sender(sender_phone: str):
    """
    Replace with your real Trip creation logic.
    Minimal example: create one draft trip per sender per day.
    """
    # Find latest draft trip for this sender
    trip_name = frappe.db.get_value("Trip", {"created_by_phone": sender_phone, "status": "Draft"}, "name")
    if trip_name:
        return frappe.get_doc("Trip", trip_name)

    trip = frappe.get_doc({
        "doctype": "Trip",
        "status": "Draft",
        "created_by_phone": sender_phone,
        "posting_date": frappe.utils.today(),
    })
    trip.insert(ignore_permissions=True)
    return trip


def _find_route(from_city: str, to_city: str):
    """
    Adjust to your real Route doctype fields.
    Example uses "Route" doctype with from_city/to_city.
    """
    route_name = frappe.db.get_value("Route", {"from_city": from_city, "to_city": to_city}, "name")
    return frappe.get_doc("Route", route_name) if route_name else None


def _send_routes_list(waba_message_doc):
    routes = frappe.db.get_all("Route", fields=["name", "from_city", "to_city"], limit=25, order_by="modified desc")
    if not routes:
        _send_reply(waba_message_doc, "No routes found in system.")
        return

    lines = ["Reply with: FromCity ToCity", "Example: Jeddah Makkah", ""]
    for r in routes:
        lines.append(f"- {r['from_city']} -> {r['to_city']}")
    _send_reply(waba_message_doc, "\n".join(lines))


def _finalize_trip_and_send_pdf(trip, ocr_history_ids: list[str], waba_message_doc):
    """
    Plug your existing Kashf PDF generator + WhatsApp send.
    """
    # Example: attach OCR records to trip (if you have child table)
    # trip.set("passengers", ...)
    trip.status = "Submitted"
    trip.save(ignore_permissions=True)
    frappe.db.commit()

    # You likely already have: send_trip_pdf_via_whatsapp(...)
    _send_reply(waba_message_doc, f"✅ Trip created: {trip.name}. Kashf will be sent.")


# -----------------------------
# Main entry: handle incoming WhatsApp message
# -----------------------------
def handle_incoming_whatsapp_message(waba_message_name: str):
    """
    Call this from your webhook handler after a WhatsApp Message record is created.
    """
    doc = frappe.get_doc("WhatsApp Message", waba_message_name)

    sender_raw = getattr(doc, "from_number", "") or getattr(doc, "sender", "") or ""
    sender_phone = normalize_phone(sender_raw)

    if not sender_phone:
        return

    if not _is_staff_phone(sender_phone):
        _send_reply(doc, "❌ Not authorized. Please contact admin.")
        return

    # Contact/session record (you already have get_or_create_contact)
    contact = get_or_create_contact(sender_phone)

    # Ensure session fields exist (create in your Contact doctype)
    state = (getattr(contact, "bot_state", None) or STATE_IDLE).upper()
    expected = int(getattr(contact, "expected_passengers", 0) or 0)

    collected_json = getattr(contact, "collected_file_urls_json", "") or "[]"
    resend_json = getattr(contact, "resend_indexes_json", "") or "[]"
    resend_ptr = int(getattr(contact, "resend_ptr", 0) or 0)

    collected = _jload(collected_json)
    resend_indexes = _jload(resend_json)

    text = (getattr(doc, "message", "") or getattr(doc, "text", "") or "").strip()
    file_url = (getattr(doc, "attach", "") or getattr(doc, "file_url", "") or "").strip()

    # ----------------------------
    # 1) If passenger count not set, ask and parse it
    # ----------------------------
    if expected <= 0 and not file_url:
        if state in (STATE_IDLE, STATE_ASK_PASSENGER_COUNT):
            n = _parse_int(text)
            if n and n > 0:
                contact.expected_passengers = n
                contact.bot_state = STATE_COLLECTING_DOCS
                contact.collected_file_urls_json = "[]"
                contact.resend_indexes_json = "[]"
                contact.resend_ptr = 0
                contact.save(ignore_permissions=True)
                frappe.db.commit()
                _send_reply(doc, f"✅ Passenger count set to {n}. Now send {n} passenger ID images (one per passenger).")
                return

            contact.bot_state = STATE_ASK_PASSENGER_COUNT
            contact.save(ignore_permissions=True)
            frappe.db.commit()
            _send_reply(doc, "How many passengers? (reply with number only)")
            return

    # ----------------------------
    # 2) If we receive media, collect it
    # ----------------------------
    if file_url:
        # Ensure we have a trip (draft)
        trip = _get_or_create_trip_for_sender(sender_phone)

        # RESEND MODE: replace specific passenger slots
        if state == STATE_RESEND_DOCS and resend_indexes:
            # Make sure list has expected length
            while len(collected) < expected:
                collected.append(None)

            idx_to_replace = resend_indexes[resend_ptr]  # 1-based
            collected[idx_to_replace - 1] = file_url
            resend_ptr += 1

            contact.collected_file_urls_json = _jdump(collected)
            contact.resend_ptr = resend_ptr
            contact.save(ignore_permissions=True)
            frappe.db.commit()

            if resend_ptr < len(resend_indexes):
                next_need = resend_indexes[resend_ptr]
                _send_reply(doc, f"✅ Received. Please resend passenger #{next_need} image.")
                return

            # Done resends -> back to collecting and run batch again
            contact.resend_indexes_json = "[]"
            contact.resend_ptr = 0
            contact.bot_state = STATE_COLLECTING_DOCS
            contact.save(ignore_permissions=True)
            frappe.db.commit()

        else:
            # Normal collect: append in order
            collected.append(file_url)
            contact.collected_file_urls_json = _jdump(collected)

            # if passenger count still unknown, ask it
            if expected <= 0:
                contact.bot_state = STATE_ASK_PASSENGER_COUNT
                contact.save(ignore_permissions=True)
                frappe.db.commit()
                _send_reply(doc, f"🧾 Document {len(collected)} received. Now reply passenger count (number only).")
                return

            contact.bot_state = STATE_COLLECTING_DOCS
            contact.save(ignore_permissions=True)
            frappe.db.commit()

        # Count how many valid slots filled
        received = len([x for x in collected if x])

        if received < expected:
            _send_reply(doc, f"✅ Document {received}/{expected} received. Send remaining {expected-received}.")
            return

        if received > expected:
            _send_reply(doc, f"⚠️ You sent {received} images but passenger count is {expected}. Reply with new passenger count.")
            contact.bot_state = STATE_ASK_PASSENGER_COUNT
            contact.save(ignore_permissions=True)
            frappe.db.commit()
            return

        # ----------------------------
        # 3) We have exactly expected docs -> run ONE Gemini batch OCR
        # ----------------------------
        try:
            out = process_passenger_images_for_trip(
                site_name=SITE_NAME,
                trip_name=trip.name,
                file_urls_in_order=collected[:expected],
                expected_count=expected,
                source="WhatsApp Message",
            )
        except Exception:
            frappe.log_error(frappe.get_traceback(), "Gemini Batch OCR failed")
            _send_reply(doc, "⚠️ OCR failed. Please resend images or contact office.")
            return

        if not out.get("ok"):
            bad = out.get("resend_indexes", [])
            contact.resend_indexes_json = _jdump(bad)
            contact.resend_ptr = 0
            contact.bot_state = STATE_RESEND_DOCS
            contact.save(ignore_permissions=True)
            frappe.db.commit()
            _send_reply(doc, f"⚠️ Please resend clearer image(s) for passenger: {bad}")
            return

        # OCR OK -> move to route step
        contact.bot_state = STATE_ASK_ROUTE
        contact.save(ignore_permissions=True)
        frappe.db.commit()
        _send_reply(doc, "✅ Documents verified. Now send route like: Jeddah Makkah (FromCity ToCity)")
        return

    # ----------------------------
    # 3) Route handling (text message)
    # ----------------------------
    if state == STATE_ASK_ROUTE:
        from_city, to_city = _parse_route_text(text)

        if not from_city or not to_city:
            _send_routes_list(doc)
            return

        route = _find_route(from_city, to_city)
        if not route:
            _send_reply(doc, f"❌ Route not found for: {from_city} -> {to_city}\nI will show routes list.")
            _send_routes_list(doc)
            return

        # Create/Load trip and finalize
        trip = _get_or_create_trip_for_sender(sender_phone)
        trip.route = route.name
        trip.from_city = getattr(route, "from_city", from_city)
        trip.to_city = getattr(route, "to_city", to_city)
        trip.save(ignore_permissions=True)
        frappe.db.commit()

        # Pull OCR IDs saved recently for this trip
        ocr_ids = frappe.db.get_all("OCR History", filters={"trip": trip.name}, pluck="name")

        _finalize_trip_and_send_pdf(trip, ocr_ids, doc)

        contact.bot_state = STATE_DONE
        contact.save(ignore_permissions=True)
        frappe.db.commit()
        return

    # ----------------------------
    # Default fallback
    # ----------------------------
    if expected <= 0:
        contact.bot_state = STATE_ASK_PASSENGER_COUNT
        contact.save(ignore_permissions=True)
        frappe.db.commit()
        _send_reply(doc, "How many passengers? (reply with number only)")
    else:
        _send_reply(doc, f"Send {expected} passenger ID images (one per passenger).")
