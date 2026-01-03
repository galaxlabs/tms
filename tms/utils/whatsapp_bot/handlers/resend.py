from tms.utils.whatsapp_bot.helpers.json_store import get_json, set_json
from tms.utils.whatsapp_bot.helpers.messaging import send_reply
from tms.utils.whatsapp_bot.flows.route_flow import ensure_route_or_ask


def is_resend_active(contact) -> bool:
    resend = get_json(contact, "resend_indexes_json", [])
    ptr = int(getattr(contact, "resend_ptr", 0) or 0)
    return bool(resend) and ptr < len(resend)


def start_resend_cycle(contact, incoming_doc, lang):
    resend_indexes = get_json(contact, "resend_indexes_json", [])
    resend_ptr = int(getattr(contact, "resend_ptr", 0) or 0)

    if resend_ptr >= len(resend_indexes):
        return

    # ✅ anti-spam lock
    state = get_json(contact, "received_files_json", {})
    last_prompt = state.get("last_resend_ptr")
    if last_prompt == resend_ptr:
        return

    state["last_resend_ptr"] = resend_ptr
    set_json(contact, "received_files_json", state)
    contact.save(ignore_permissions=True)

    n = int(resend_indexes[resend_ptr])  # passenger number (1-based)
    send_reply(incoming_doc, "resend_document", lang, n=n)


def handle_resend_media(ctx):
    doc = ctx["doc"]
    contact = ctx["contact"]
    lang = ctx["lang"]

    doc.reload()
    file_url = (doc.attach or "").strip()
    if not file_url:
        send_reply(doc, "no_attachment", lang, fallback="🕐 I received your message, but no file was attached.")
        return

    urls = get_json(contact, "collected_file_urls_json", [])
    resend_indexes = get_json(contact, "resend_indexes_json", [])
    ptr = int(getattr(contact, "resend_ptr", 0) or 0)

    if not resend_indexes or ptr >= len(resend_indexes):
        # cleanup
        set_json(contact, "resend_indexes_json", [])
        contact.resend_ptr = 0
        contact.bot_state = "COLLECTING_DOCS"
        contact.save(ignore_permissions=True)
        return

    # ✅ replace correct passenger slot (1-based → 0-based)
    passenger_no = int(resend_indexes[ptr])
    array_index = passenger_no - 1

    while len(urls) <= array_index:
        urls.append("")

    urls[array_index] = file_url
    set_json(contact, "collected_file_urls_json", urls)

    # advance
    contact.resend_ptr = ptr + 1
    contact.save(ignore_permissions=True)

    # ask next resend
    if contact.resend_ptr < len(resend_indexes):
        next_no = int(resend_indexes[contact.resend_ptr])
        send_reply(doc, "resend_document", lang, n=next_no)
        return

    # all resends received → clear resend state
    set_json(contact, "resend_indexes_json", [])
    contact.resend_ptr = 0
    contact.bot_state = "COLLECTING_DOCS"
    contact.save(ignore_permissions=True)

    # re-run OCR with updated urls (lazy import avoids circular)
    from tms.utils.whatsapp_bot.services.ocr_service import run_batch_ocr
    result = run_batch_ocr(ctx)
    if not result.get("ok"):
        return

    ensure_route_or_ask(ctx)
