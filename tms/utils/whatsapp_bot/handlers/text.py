# tms/utils/whatsapp_bot/handlers/text.py
import frappe
from tms.utils.whatsapp_bot.helpers.messaging import send_reply
from tms.utils.whatsapp_bot.flows.trip_flow import get_or_create_trip
from tms.utils.bot_settings import get_settings


def handle_text(ctx):
    """
    Handles text messages:
    - reset/start/new/begin command
    - passenger count entry (WAITING_PASSENGER_COUNT)
    - fallback for now
    """
    doc = ctx["doc"]
    contact = ctx["contact"]
    lang = ctx["lang"]
    driver = ctx["driver"]

    text = (doc.message or "").strip()
    if not text:
        send_reply(doc, "ask_passenger_count_invalid", lang, fallback="ℹ️ Please send a message.")
        return

    # Debug (safe inside function)
    frappe.log_error(
        "WA BOT TEXT",
        f"contact={getattr(contact,'name',None)} state={getattr(contact,'bot_state',None)} text={text}",
    )

    # -----------------------------
    # ✅ Reset / Start command
    # -----------------------------
    t = text.lower().strip()
    if t in ("start", "reset", "new", "begin"):
        # reset contact state
        contact.bot_state = "WAITING_PASSENGER_COUNT"
        contact.expected_passengers = 0
        contact.received_images = 0
        contact.collected_file_urls_json = "[]"
        contact.resend_indexes_json = "[]"
        contact.resend_ptr = 0
        contact.current_trip = None
        contact.save(ignore_permissions=True)

        send_reply(
            doc,
            "ask_passenger_count_invalid",
            lang,
            fallback="✅ Started. Send number of passengers (example: 3).",
        )
        return

    # -----------------------------
    # Passenger count handling
    # -----------------------------
    state = (getattr(contact, "bot_state", "") or "").upper()
    if state in ("", "WAITING_PASSENGER_COUNT", "START"):
        n = _extract_int(text)
        if not n or n <= 0:
            send_reply(
                doc,
                "ask_passenger_count_invalid",
                lang,
                fallback="ℹ️ Please send number of passengers only (example: 3).",
            )
            return

        settings, _ = get_settings()
        max_p = int(settings.max_passengers or 0)
        if max_p and n > max_p:
            send_reply(
                doc,
                "max_passengers_exceeded",
                lang,
                fallback="❗ Max passengers allowed is {max}.",
                max=max_p,
            )
            return

        contact.expected_passengers = int(n)
        contact.bot_state = "COLLECTING_DOCS"
        contact.save(ignore_permissions=True)

        # ensure trip exists
        trip = get_or_create_trip(driver, contact)
        ctx["trip"] = trip

        send_reply(
            doc,
            "ask_send_docs",
            lang,
            fallback="✅ Passenger count saved: {expected}. Now send {expected} documents (one per passenger).",
            expected=n,
        )
        return

    # -----------------------------
    # Temporary fallback
    # -----------------------------
    send_reply(
        doc,
        "ask_passenger_count_invalid",
        lang,
        fallback="ℹ️ Send 'reset' to start again, or send passenger count (example: 3).",
    )


def _extract_int(text: str):
    digits = ""
    for ch in text:
        if ch.isdigit():
            digits += ch
        elif digits:
            break
    try:
        return int(digits) if digits else None
    except Exception:
        return None

# # tms/utils/whatsapp_bot/handlers/text.py
# import frappe
# from tms.utils.whatsapp_bot.helpers.messaging import send_reply
# from tms.utils.whatsapp_bot.helpers.json_store import get_json, set_json
# from tms.utils.whatsapp_bot.flows.trip_flow import get_or_create_trip
# from tms.utils.bot_settings import get_settings

# frappe.log_error("WA BOT TEXT", f"state={contact.bot_state} text={text} contact={contact.name}")


# def handle_text(ctx):
#     """
#     Minimal working text handler.
#     Later we expand: route selection, passenger count, menu commands, etc.
#     """
#     doc = ctx["doc"]
#     contact = ctx["contact"]
#     lang = ctx["lang"]
#     driver = ctx["driver"]

#     text = (doc.message or "").strip()
#     if not text:
#         send_reply(doc, "ask_passenger_count_invalid", lang, fallback="ℹ️ Please send a message.")
#         return

#     # If we are waiting for passenger count, try parse digits
#     state = (getattr(contact, "bot_state", "") or "").upper()
#     if state in ("", "WAITING_PASSENGER_COUNT", "START"):
#         n = _extract_int(text)
#         if not n or n <= 0:
#             send_reply(doc, "ask_passenger_count_invalid", lang, fallback="ℹ️ Please send number of passengers only (example: 3).")
#             return

#         settings, _ = get_settings()
#         max_p = int(settings.max_passengers or 0)
#         if max_p and n > max_p:
#             send_reply(doc, "max_passengers_exceeded", lang, fallback="❗ Max passengers allowed is {max}.", max=max_p)
#             return

#         contact.expected_passengers = int(n)
#         contact.bot_state = "COLLECTING_DOCS"
#         contact.save(ignore_permissions=True)

#         # ensure trip exists
#         trip = get_or_create_trip(driver, contact)
#         ctx["trip"] = trip

#         send_reply(doc, "ask_send_docs", lang,
#                   fallback="✅ Passenger count saved: {expected}. Now send {expected} documents (one per passenger).",
#                   expected=n)
#         return

#     # Default fallback for other states (for now)
#     send_reply(doc, "ask_passenger_count_invalid", lang, fallback="ℹ️ Please send number of passengers only (example: 3).")


# def _extract_int(text: str):
#     digits = ""
#     for ch in text:
#         if ch.isdigit():
#             digits += ch
#         elif digits:
#             break
#     try:
#         return int(digits) if digits else None
#     except Exception:
#         return None
