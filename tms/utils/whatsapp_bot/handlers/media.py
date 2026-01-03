# # /home/xg/xg-b/apps/tms/tms/utils/whatsapp_bot/handlers/media.py
# apps/tms/tms/utils/whatsapp_bot/handlers/media.py

import frappe
from tms.utils.whatsapp_bot.helpers.json_store import get_json, set_json
from tms.utils.whatsapp_bot.helpers.messaging import send_reply
from tms.utils.passenger_ocr_service import process_passenger_images_batch


def handle_media(ctx):
    doc = ctx["doc"]
    contact = ctx["contact"]
    lang = ctx["lang"]

    file_url = (doc.attach or "").strip()
    if not file_url:
        return

    expected = int(getattr(contact, "expected_passengers", 0) or 0)
    if expected <= 0:
        send_reply(
            doc,
            "ask_passenger_count_invalid",
            lang,
            fallback="ℹ️ Please send number of passengers first (example: 3).",
        )
        return

    # Load & normalize urls list
    urls = get_json(contact, "collected_file_urls_json", []) or []
    if not isinstance(urls, list):
        urls = []

    # Keep only expected size
    urls = urls[:expected]

    # Ensure list has expected slots ("" placeholders)
    while len(urls) < expected:
        urls.append("")

    # Fill first empty slot
    placed = False
    for i in range(expected):
        if not urls[i]:
            urls[i] = file_url
            placed = True
            break

    # If no empty slot, user sent extra file; do not corrupt state
    if not placed:
        received = len([u for u in urls if u])
        send_reply(
            doc,
            "doc_extra_ignored",
            lang,
            fallback="✅ I already received {received}/{expected}. Extra file ignored. Type 'reset' to start over.",
            received=received,
            expected=expected,
        )
        return

    set_json(contact, "collected_file_urls_json", urls)

    received = len([u for u in urls if u])
    contact.received_images = received
    contact.bot_state = "COLLECTING_DOCS"
    contact.save(ignore_permissions=True)

    if received < expected:
        send_reply(
            doc,
            "doc_progress",
            lang,
            fallback="✅ Document {received}/{expected} received. Remaining: {remaining}.",
            received=received,
            expected=expected,
            remaining=(expected - received),
        )
        return

    # All received -> run OCR once
    _run_ocr_and_next(doc, contact, lang, urls)


def _run_ocr_and_next(doc, contact, lang, urls):
    expected = int(getattr(contact, "expected_passengers", 0) or 0)
    urls = (urls or [])[:expected]

    trip_name = contact.current_trip
    if not trip_name or not frappe.db.exists("Trip", trip_name):
        send_reply(doc, "trip_missing", lang, fallback="❗ Trip was not created. Type 'reset' and start again.")
        return

    contact.bot_state = "OCR_PROCESSING"
    contact.save(ignore_permissions=True)

    res = process_passenger_images_batch(
        trip_name=trip_name,
        file_urls=urls,
        waba_message=doc.name,  # WhatsApp Message docname
    )

    if res.get("ok"):
        set_json(contact, "received_files_json", {"passengers": res.get("passengers") or []})
        set_json(contact, "resend_indexes_json", [])
        contact.resend_ptr = 0
        contact.bot_state = "WAITING_ROUTE"
        contact.save(ignore_permissions=True)

        from tms.utils.whatsapp_bot.flows.route_flow import send_route_list
        send_route_list(doc, contact, lang)
        return

    resend = res.get("resend_indexes") or []
    set_json(contact, "resend_indexes_json", resend)
    contact.resend_ptr = 0
    contact.bot_state = "RESENDING_DOCS"
    contact.save(ignore_permissions=True)

    # Use resend helper (has anti-spam lock)
    from tms.utils.whatsapp_bot.handlers.resend import start_resend_cycle
    start_resend_cycle(contact, doc, lang)

# apps/tms/tms/utils/whatsapp_bot/handlers/media.py
# import frappe
# from tms.utils.whatsapp_bot.helpers.json_store import get_json, set_json
# from tms.utils.whatsapp_bot.helpers.messaging import send_reply
# from tms.utils.passenger_ocr_service import process_passenger_images_batch


# def handle_media(ctx):
#     doc = ctx["doc"]
#     contact = ctx["contact"]
#     lang = ctx["lang"]
#     driver_name = ctx.get("driver_name") or (doc.profile_name or "").strip() or "Driver"

#     state = (getattr(contact, "bot_state", "") or "").strip().upper()
#     file_url = (getattr(doc, "attach", "") or "").strip()

#     if not file_url:
#         return

#     if state == "OCR_PROCESSING":
#         send_reply(doc, "ocr_processing", lang, fallback="⏳ Processing your documents. Please wait a moment.", driver_name=driver_name)
#         return

#     expected = int(getattr(contact, "expected_passengers", 0) or 0)
#     if expected <= 0:
#         send_reply(
#             doc,
#             "ask_passenger_count_invalid",
#             lang,
#             fallback="ℹ️ Send number of passengers first (example: 3).",
#             driver_name=driver_name,
#         )
#         return

#     urls = get_json(contact, "collected_file_urls_json", []) or []

#     if state != "RESENDING_DOCS" and file_url in urls:
#         return

#     # RESENDING MODE
#     if state == "RESENDING_DOCS":
#         resend = get_json(contact, "resend_indexes_json", []) or []
#         ptr = int(getattr(contact, "resend_ptr", 0) or 0)

#         if not resend or ptr >= len(resend):
#             return _run_ocr_and_next(doc, contact, lang, driver_name)

#         n = int(resend[ptr])
#         idx0 = n - 1

#         while len(urls) < expected:
#             urls.append("")

#         urls[idx0] = file_url
#         set_json(contact, "collected_file_urls_json", urls)

#         new_ptr = ptr + 1
#         frappe.db.set_value(contact.doctype, contact.name, {"resend_ptr": new_ptr}, update_modified=False)
#         contact.resend_ptr = new_ptr

#         if new_ptr < len(resend):
#             next_n = int(resend[new_ptr])
#             send_reply(
#                 doc,
#                 "resend_document",
#                 lang,
#                 fallback="⚠️ Passenger #{n} document is not clear. Please resend passenger #{n}.",
#                 n=next_n,
#                 driver_name=driver_name,
#             )
#             return

#         return _run_ocr_and_next(doc, contact, lang, driver_name)

#     # NORMAL COLLECTING MODE
#     urls.append(file_url)
#     urls = urls[:expected]
#     set_json(contact, "collected_file_urls_json", urls)

#     received = len([u for u in urls if u])

#     frappe.db.set_value(
#         contact.doctype,
#         contact.name,
#         {"received_images": received, "bot_state": "COLLECTING_DOCS"},
#         update_modified=False,
#     )
#     contact.received_images = received
#     contact.bot_state = "COLLECTING_DOCS"

#     if received < expected:
#         send_reply(
#             doc,
#             "doc_progress",
#             lang,
#             fallback="✅ Document {received}/{expected} received. Remaining: {remaining}.",
#             received=received,
#             expected=expected,
#             remaining=(expected - received),
#             driver_name=driver_name,
#         )
#         return

#     return _run_ocr_and_next(doc, contact, lang, driver_name)


# def _run_ocr_and_next(doc, contact, lang, driver_name: str):
#     expected = int(getattr(contact, "expected_passengers", 0) or 0)
#     urls = (get_json(contact, "collected_file_urls_json", []) or [])[:expected]

#     trip_name = getattr(contact, "current_trip", None)
#     if not trip_name or not frappe.db.exists("Trip", trip_name):
#         send_reply(doc, "trip_missing", lang, fallback="❗ Trip not found. Type 'reset' and start again.", driver_name=driver_name)
#         return

#     frappe.db.set_value(contact.doctype, contact.name, {"bot_state": "OCR_PROCESSING"}, update_modified=False)
#     contact.bot_state = "OCR_PROCESSING"

#     # Nice message BEFORE OCR starts
#     send_reply(
#         doc,
#         "all_docs_received_processing",
#         lang,
#         fallback="✅ All documents received ({received}/{expected}). Now processing…",
#         received=len([u for u in urls if u]),
#         expected=expected,
#         driver_name=driver_name,
#     )

#     res = process_passenger_images_batch(
#         trip_name=trip_name,
#         file_urls=urls,
#         waba_message=doc.name,
#     )

#     if res.get("ok"):
#         set_json(contact, "received_files_json", {"passengers": res.get("passengers") or []})
#         set_json(contact, "resend_indexes_json", [])

#         frappe.db.set_value(contact.doctype, contact.name, {"resend_ptr": 0, "bot_state": "WAITING_ROUTE"}, update_modified=False)
#         contact.resend_ptr = 0
#         contact.bot_state = "WAITING_ROUTE"

#         from tms.utils.whatsapp_bot.flows.route_flow import send_route_list
#         send_route_list(doc, contact, lang)
#         return

#     resend = res.get("resend_indexes") or []
#     set_json(contact, "resend_indexes_json", resend)

#     frappe.db.set_value(contact.doctype, contact.name, {"resend_ptr": 0, "bot_state": "RESENDING_DOCS"}, update_modified=False)
#     contact.resend_ptr = 0
#     contact.bot_state = "RESENDING_DOCS"

#     n = int(resend[0]) if resend else 1
#     send_reply(
#         doc,
#         "resend_document",
#         lang,
#         fallback="⚠️ Passenger #{n} document is not clear. Please resend passenger #{n}.",
#         n=n,
#         driver_name=driver_name,
#     )


# import frappe
# from tms.utils.whatsapp_bot.helpers.json_store import get_json, set_json
# from tms.utils.whatsapp_bot.helpers.messaging import send_reply
# from tms.utils.passenger_ocr_service import process_passenger_images_batch


# def handle_media(ctx):
#     """
#     Handles incoming media (image/document) for passenger docs.

#     States:
#       - COLLECTING_DOCS: collect until expected count reached, then OCR once
#       - RESENDING_DOCS: replace only specific passenger indexes, then OCR again
#       - OCR_PROCESSING: ignore (optional, but safe)
#       - WAITING_ROUTE / DONE: ignore media (optional)
#     """
#     doc = ctx["doc"]
#     contact = ctx["contact"]
#     lang = ctx["lang"]

#     state = (getattr(contact, "bot_state", "") or "").strip().upper()
#     file_url = (getattr(doc, "attach", "") or "").strip()

#     # Must have attachment URL
#     if not file_url:
#         return

#     # If OCR already running, ignore extra media to prevent mixing batches
#     if state == "OCR_PROCESSING":
#         send_reply(doc, "ocr_processing", lang, fallback="⏳ Processing your documents. Please wait a moment.")
#         return

#     expected = int(getattr(contact, "expected_passengers", 0) or 0)
#     if expected <= 0:
#         send_reply(
#             doc,
#             "ask_passenger_count_invalid",
#             lang,
#             fallback="ℹ️ Send number of passengers first (example: 3).",
#         )
#         return

#     # Load current URLs list
#     urls = get_json(contact, "collected_file_urls_json", []) or []

#     # Avoid duplicate webhook retries adding same file twice (in normal collecting)
#     # NOTE: In resend mode we allow duplicates because replacing may repeat same URL.
#     if state != "RESENDING_DOCS" and file_url in urls:
#         return

#     # ---------------------------------------------------------
#     # RESENDING MODE
#     # ---------------------------------------------------------
#     if state == "RESENDING_DOCS":
#         resend = get_json(contact, "resend_indexes_json", []) or []
#         ptr = int(getattr(contact, "resend_ptr", 0) or 0)

#         # Safety fallback: if resend list missing or finished, just OCR what we have
#         if not resend or ptr >= len(resend):
#             return _run_ocr_and_next(doc, contact, lang)

#         # Which passenger to replace (1-based index)
#         n = int(resend[ptr])
#         idx0 = n - 1  # 0-based

#         # Ensure urls length at least expected
#         while len(urls) < expected:
#             urls.append("")

#         # Replace that passenger document
#         urls[idx0] = file_url
#         set_json(contact, "collected_file_urls_json", urls)

#         # Advance pointer (single update, no save)
#         new_ptr = ptr + 1
#         frappe.db.set_value(
#             contact.doctype,
#             contact.name,
#             {"resend_ptr": new_ptr},
#             update_modified=False,
#         )
#         contact.resend_ptr = new_ptr

#         # Ask next resend if still pending
#         if new_ptr < len(resend):
#             next_n = int(resend[new_ptr])
#             send_reply(
#                 doc,
#                 "resend_document",
#                 lang,
#                 fallback="⚠️ Passenger #{n} document is not clear. Please resend passenger #{n}.",
#                 n=next_n,
#             )
#             return

#         # Done resends -> rerun OCR
#         return _run_ocr_and_next(doc, contact, lang)

#     # ---------------------------------------------------------
#     # NORMAL COLLECTING MODE
#     # ---------------------------------------------------------
#     # Append and cap to expected
#     urls.append(file_url)
#     urls = urls[:expected]
#     set_json(contact, "collected_file_urls_json", urls)

#     received = len([u for u in urls if u])

#     # Single update to avoid lock-heavy contact.save()
#     frappe.db.set_value(
#         contact.doctype,
#         contact.name,
#         {"received_images": received, "bot_state": "COLLECTING_DOCS"},
#         update_modified=False,
#     )
#     contact.received_images = received
#     contact.bot_state = "COLLECTING_DOCS"

#     # Not complete yet -> progress message
#     if received < expected:
#         send_reply(
#             doc,
#             "doc_progress",
#             lang,
#             fallback="✅ Document {received}/{expected} received. Remaining: {remaining}.",
#             received=received,
#             expected=expected,
#             remaining=(expected - received),
#         )
#         return

#     # Complete -> run OCR once
#     return _run_ocr_and_next(doc, contact, lang)


# def _run_ocr_and_next(doc, contact, lang):
#     """
#     Runs batch OCR for the collected docs and:
#       - if ok: stores passengers, clears resend list, moves to WAITING_ROUTE, sends route list
#       - if not ok: stores resend indexes, moves to RESENDING_DOCS, asks first resend
#     """
#     expected = int(getattr(contact, "expected_passengers", 0) or 0)
#     urls = (get_json(contact, "collected_file_urls_json", []) or [])[:expected]

#     # Trip must exist now
#     trip_name = getattr(contact, "current_trip", None)
#     if not trip_name or not frappe.db.exists("Trip", trip_name):
#         send_reply(
#             doc,
#             "trip_missing",
#             lang,
#             fallback="❗ Trip not found. Type 'reset' and start again.",
#         )
#         return

#     # Mark processing
#     frappe.db.set_value(
#         contact.doctype,
#         contact.name,
#         {"bot_state": "OCR_PROCESSING"},
#         update_modified=False,
#     )
#     contact.bot_state = "OCR_PROCESSING"

#     # IMPORTANT: pass WhatsApp Message docname (doc.name), not message_id
#     res = process_passenger_images_batch(
#         trip_name=trip_name,
#         file_urls=urls,
#         waba_message=doc.name,
#     )

#     # ----------------------------
#     # OCR OK -> move to route
#     # ----------------------------
#     if res.get("ok"):
#         set_json(contact, "received_files_json", {"passengers": res.get("passengers") or []})
#         set_json(contact, "resend_indexes_json", [])

#         frappe.db.set_value(
#             contact.doctype,
#             contact.name,
#             {"resend_ptr": 0, "bot_state": "WAITING_ROUTE"},
#             update_modified=False,
#         )
#         contact.resend_ptr = 0
#         contact.bot_state = "WAITING_ROUTE"

#         from tms.utils.whatsapp_bot.flows.route_flow import send_route_list
#         send_route_list(doc, contact, lang)
#         return

#     # ----------------------------
#     # OCR NOT OK -> resend flow
#     # ----------------------------
#     resend = res.get("resend_indexes") or []
#     set_json(contact, "resend_indexes_json", resend)

#     frappe.db.set_value(
#         contact.doctype,
#         contact.name,
#         {"resend_ptr": 0, "bot_state": "RESENDING_DOCS"},
#         update_modified=False,
#     )
#     contact.resend_ptr = 0
#     contact.bot_state = "RESENDING_DOCS"

#     n = int(resend[0]) if resend else 1
#     send_reply(
#         doc,
#         "resend_document",
#         lang,
#         fallback="⚠️ Passenger #{n} document is not clear. Please resend passenger #{n}.",
#         n=n,
#     )
