# apps/tms/tms/utils/whatsapp_bot/handlers/text.py

import frappe
from tms.utils.whatsapp_bot.helpers.messaging import send_reply
from tms.utils.whatsapp_bot.helpers.json_store import get_json, set_json
from tms.utils.whatsapp_bot.flows.trip_flow import get_or_create_trip
from tms.utils.whatsapp_bot.flows.route_flow import handle_route_choice
from tms.utils.bot_settings import get_settings


# def handle_text(ctx):
#     doc = ctx["doc"]
#     contact = ctx["contact"]
#     lang = ctx["lang"]
#     driver = ctx["driver"]

#     text = (doc.message or "").strip()
#     t = text.lower().strip()

#     frappe.log_error(
#         "WA BOT TEXT",
#         f"contact={contact.name} state={getattr(contact,'bot_state',None)} text={repr(text)} mid={getattr(doc,'message_id',None)}",
#     )

#     if not text:
#         send_reply(doc, "ask_passenger_count_invalid", lang, fallback="ℹ️ Please send a message.")
#         return

#     # ---------------------------------------------------------
#     # START/RESET commands
#     # ---------------------------------------------------------
#     if t in ("start", "reset", "new", "begin"):
#         _reset_contact_state(contact)
#         send_reply(
#             doc,
#             "ask_passenger_count_invalid",
#             lang,
#             fallback="✅ Started. Send number of passengers (example: 3).",
#         )
#         return

#     state = _get_state(contact)

#     # ---------------------------------------------------------
#     # RESEND MODE: user must send media, not text
#     # ---------------------------------------------------------
#     if state in ("RESENDING_DOCS", "RESEND_DOCS"):
#         resend = get_json(contact, "resend_indexes_json", []) or []
#         ptr = int(getattr(contact, "resend_ptr", 0) or 0)

#         if ptr < len(resend):
#             n = int(resend[ptr])
#             send_reply(
#                 doc,
#                 "resend_document",
#                 lang,
#                 fallback="⚠️ Passenger #{n} document is not clear. Please resend passenger #{n} as an image/document.",
#                 n=n,
#             )
#             return

#         send_reply(
#             doc,
#             "resend_done_wait",
#             lang,
#             fallback="✅ Resend list finished. Please send the last required document again, or type 'reset'.",
#         )
#         return

#     # ---------------------------------------------------------
#     # COLLECTING DOCS: guide user to send docs
#     # ---------------------------------------------------------
#     if state == "COLLECTING_DOCS":
#         expected = int(getattr(contact, "expected_passengers", 0) or 0)
#         received = int(getattr(contact, "received_images", 0) or 0)
#         remaining = max(expected - received, 0)

#         send_reply(
#             doc,
#             "ask_send_docs",
#             lang,
#             fallback="📎 Please send passenger documents. Received: {received}/{expected}. Remaining: {remaining}.",
#             received=received,
#             expected=expected,
#             remaining=remaining,
#         )
#         return

#     # ---------------------------------------------------------
#     # ROUTE SELECTION
#     # ---------------------------------------------------------
#     if state == "WAITING_ROUTE":
#         n = _extract_int(text)
#         if not n:
#             send_reply(
#                 doc,
#                 "route_invalid",
#                 lang,
#                 fallback="❗ Please reply with the route *number* from the list (example: 2).",
#             )
#             return

#         ok = handle_route_choice(ctx, n)
#         if not ok:
#             send_reply(
#                 doc,
#                 "route_invalid",
#                 lang,
#                 fallback="❗ Please reply with the route *number* from the list (example: 2).",
#             )
#         return

#     # ---------------------------------------------------------
#     # PASSENGER COUNT (THIS IS THE CRITICAL FIX)
#     # ---------------------------------------------------------
#     if state in ("", "WAITING_PASSENGER_COUNT", "START"):
#         n = _extract_int(text)
#         if not n or n <= 0:
#             send_reply(
#                 doc,
#                 "ask_passenger_count_invalid",
#                 lang,
#                 fallback="ℹ️ Please send number of passengers only (example: 3).",
#             )
#             return

#         settings, _ = get_settings()
#         max_p = int(getattr(settings, "max_passengers", 0) or 0)
#         if max_p and n > max_p:
#             send_reply(
#                 doc,
#                 "max_passengers_exceeded",
#                 lang,
#                 fallback="❗ Max passengers allowed is {max}.",
#                 max=max_p,
#             )
#             return

#         # ✅ IMPORTANT: create/reuse trip FIRST (so trip_flow can safely reset defaults)
#         trip = get_or_create_trip(driver, contact)
#         ctx["trip"] = trip

#         # ✅ HARD RESET collection state so bot never “asks extra images”
#         contact.expected_passengers = int(n)
#         contact.received_images = 0
#         contact.resend_ptr = 0
#         contact.bot_state = "COLLECTING_DOCS"

#         set_json(contact, "collected_file_urls_json", [])
#         set_json(contact, "resend_indexes_json", [])
#         set_json(contact, "received_files_json", {})

#         contact.save(ignore_permissions=True)

#         send_reply(
#             doc,
#             "ask_send_docs",
#             lang,
#             fallback="✅ Passenger count saved: {expected}. Now send {expected} documents (one per passenger).",
#             expected=n,
#         )
#         return

#     # ---------------------------------------------------------
#     # Default
#     # ---------------------------------------------------------
#     send_reply(
#         doc,
#         "unknown_state",
#         lang,
#         fallback="ℹ️ I’m not sure what to do in the current step. Type 'reset' to start again.",
#     )
def handle_text(ctx):
    doc = ctx["doc"]
    contact = ctx["contact"]
    lang = ctx["lang"]
    driver = ctx["driver"]

    text = (doc.message or "").strip()
    t = text.lower().strip()

    frappe.log_error(
        "WA BOT TEXT",
        f"contact={contact.name} state={getattr(contact,'bot_state',None)} text={repr(text)} mid={getattr(doc,'message_id',None)}",
    )

    # templates-only: if empty text, just show the normal prompt again
    if not text:
        send_reply(doc, "ask_passenger_count_invalid", lang, ctx=ctx)
        return

    # ---------------------------------------------------------
    # HELP / MENU
    # ---------------------------------------------------------
    if t in ("help", "menu", "?"):
        send_reply(doc, "help_menu", lang, ctx=ctx)
        return

    # ---------------------------------------------------------
    # STATUS command (self-debug)
    # ---------------------------------------------------------
    if t in ("status", "state", "check", "info"):
        expected = int(getattr(contact, "expected_passengers", 0) or 0)
        received = int(getattr(contact, "received_images", 0) or 0)
        state = _get_state(contact) or "UNKNOWN"

        trip = getattr(contact, "current_trip", None) or "-"
        route = getattr(contact, "route", None) or "-"

        resend = "-"
        resend_indexes = get_json(contact, "resend_indexes_json", []) or []
        ptr = int(getattr(contact, "resend_ptr", 0) or 0)
        if resend_indexes and ptr < len(resend_indexes):
            resend = f"#{int(resend_indexes[ptr])}"
        elif resend_indexes:
            resend = "DONE"

        send_reply(
            doc,
            "status_message",
            lang,
            ctx=ctx,
            state=state,
            expected=expected,
            received=received,
            route=route,
            trip=trip,
            resend=resend,
        )
        send_reply(doc, "status_hint", lang, ctx=ctx)
        return

    # ---------------------------------------------------------
    # ROUTE command: show route list again
    # ---------------------------------------------------------
    if t in ("route", "routes", "list"):
        # show route list any time (useful if user forgot numbers)
        send_reply(doc, "route_list_again", lang, ctx=ctx)

        from tms.utils.whatsapp_bot.flows.route_flow import send_route_list
        send_route_list(doc, contact, lang)
        return

    # ---------------------------------------------------------
    # CANCEL command: reset everything
    # ---------------------------------------------------------
    if t in ("cancel", "stop"):
        _reset_contact_state(contact)
        send_reply(doc, "cancel_ok", lang, ctx=ctx)
        return

    # ---------------------------------------------------------
    # BACK command: go one step back (safe minimal mapping)
    # ---------------------------------------------------------
    if t == "back":
        st = _get_state(contact)

        if st == "WAITING_ROUTE":
            # go back to doc collecting
            contact.bot_state = "COLLECTING_DOCS"

        elif st in ("RESENDING_DOCS", "RESEND_DOCS"):
            # stop resend loop and go back to collecting
            contact.bot_state = "COLLECTING_DOCS"
            contact.resend_ptr = 0
            set_json(contact, "resend_indexes_json", [])

        elif st == "COLLECTING_DOCS":
            # go back to passenger count
            contact.bot_state = "WAITING_PASSENGER_COUNT"
            contact.expected_passengers = 0
            contact.received_images = 0
            set_json(contact, "collected_file_urls_json", [])
            set_json(contact, "received_files_json", {})

        else:
            # unknown -> safest
            contact.bot_state = "WAITING_PASSENGER_COUNT"

        contact.save(ignore_permissions=True)
        send_reply(doc, "back_ok", lang, ctx=ctx)
        return

    # ---------------------------------------------------------
    # START/RESET commands
    # ---------------------------------------------------------
    if t in ("start", "reset", "new", "begin"):
        _reset_contact_state(contact)
        send_reply(doc, "ask_passenger_count", lang, ctx=ctx)
        return

    state = _get_state(contact)

    # ---------------------------------------------------------
    # RESEND MODE: user must send media, not text
    # ---------------------------------------------------------
    if state in ("RESENDING_DOCS", "RESEND_DOCS"):
        resend = get_json(contact, "resend_indexes_json", []) or []
        ptr = int(getattr(contact, "resend_ptr", 0) or 0)

        if ptr < len(resend):
            n = int(resend[ptr])
            send_reply(doc, "resend_document", lang, ctx=ctx, n=n)
            return

        send_reply(doc, "resend_done_wait", lang, ctx=ctx)
        return

    # ---------------------------------------------------------
    # COLLECTING DOCS: guide user to send docs
    # ---------------------------------------------------------
    if state == "COLLECTING_DOCS":
        expected = int(getattr(contact, "expected_passengers", 0) or 0)
        received = int(getattr(contact, "received_images", 0) or 0)
        remaining = max(expected - received, 0)

        send_reply(
            doc,
            "ask_send_docs",
            lang,
            ctx=ctx,
            received=received,
            expected=expected,
            remaining=remaining,
        )
        return

    # ---------------------------------------------------------
    # ROUTE SELECTION
    # ---------------------------------------------------------
    if state == "WAITING_ROUTE":
        n = _extract_int(text)
        if not n:
            send_reply(doc, "route_invalid", lang, ctx=ctx)
            return

        ok = handle_route_choice(ctx, n)
        if not ok:
            send_reply(doc, "route_invalid", lang, ctx=ctx)
        return

    # ---------------------------------------------------------
    # PASSENGER COUNT (critical)
    # ---------------------------------------------------------
    if state in ("", "WAITING_PASSENGER_COUNT", "START"):
        n = _extract_int(text)
        if not n or n <= 0:
            send_reply(doc, "ask_passenger_count_invalid", lang, ctx=ctx)
            return

        settings, _ = get_settings()
        max_p = int(getattr(settings, "max_passengers", 0) or 0)
        if max_p and n > max_p:
            send_reply(doc, "max_passengers_exceeded", lang, ctx=ctx, max=max_p)
            return

        # create/reuse trip FIRST
        trip = get_or_create_trip(driver, contact)
        ctx["trip"] = trip

        # hard reset collection state
        contact.expected_passengers = int(n)
        contact.received_images = 0
        contact.resend_ptr = 0
        contact.bot_state = "COLLECTING_DOCS"

        set_json(contact, "collected_file_urls_json", [])
        set_json(contact, "resend_indexes_json", [])
        set_json(contact, "received_files_json", {})

        contact.save(ignore_permissions=True)

        send_reply(doc, "passenger_count_saved", lang, ctx=ctx, expected=n)
        return

    # ---------------------------------------------------------
    # Default
    # ---------------------------------------------------------
    send_reply(doc, "unknown_state", lang, ctx=ctx)


def _get_state(contact) -> str:
    return (getattr(contact, "bot_state", "") or "").strip().upper()


def _reset_contact_state(contact):
    contact.bot_state = "WAITING_PASSENGER_COUNT"
    contact.expected_passengers = 0
    contact.received_images = 0
    contact.resend_ptr = 0
    contact.current_trip = None

    set_json(contact, "collected_file_urls_json", [])
    set_json(contact, "resend_indexes_json", [])
    set_json(contact, "received_files_json", {})

    contact.save(ignore_permissions=True)


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
