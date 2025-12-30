from tms.utils.whatsapp_bot.helpers.json_store import get_json, set_json
from tms.utils.whatsapp_bot.helpers.messaging import send_reply
from tms.utils.whatsapp_bot.flows.route_flow import ensure_route_or_ask

def is_resend_active(contact) -> bool:
    resend = get_json(contact, "resend_indexes_json", [])
    return bool(resend)

def handle_resend_media(ctx):
    doc = ctx["doc"]
    contact = ctx["contact"]
    lang = ctx["lang"]

    file_url = (doc.attach or "").strip()
    if not file_url:
        send_reply(doc, "no_attachment", lang, fallback="🕐 I received your message, but no file was attached.")
        return

    urls = get_json(contact, "collected_file_urls_json", [])
    resend_indexes = get_json(contact, "resend_indexes_json", [])
    ptr = int(getattr(contact, "resend_ptr", 0) or 0)

    if not resend_indexes or ptr >= len(resend_indexes):
        # Safety cleanup
        set_json(contact, "resend_indexes_json", [])
        contact.resend_ptr = 0
        contact.bot_state = "COLLECTING_DOCS"
        contact.save(ignore_permissions=True)
        return

    n = resend_indexes[ptr]   # 1-based passenger number
    idx = n - 1

    # ensure list length
    while len(urls) <= idx:
        urls.append("")

    # replace slot
    urls[idx] = file_url
    set_json(contact, "collected_file_urls_json", urls)

    # advance pointer
    contact.resend_ptr = ptr + 1
    contact.save(ignore_permissions=True)

    # ask next resend
    if contact.resend_ptr < len(resend_indexes):
        next_n = resend_indexes[contact.resend_ptr]
        send_reply(doc, "resend_document", lang,
                   fallback="⚠️ Passenger #{n} document is not clear. Please resend passenger #{n}.",
                   n=next_n)
        return

    # all resends received → clear resend state
    set_json(contact, "resend_indexes_json", [])
    contact.resend_ptr = 0
    contact.bot_state = "COLLECTING_DOCS"
    contact.save(ignore_permissions=True)

    # ✅ Lazy import here (prevents circular imports)
    from tms.utils.whatsapp_bot.services.ocr_service import run_batch_ocr

    result = run_batch_ocr(ctx)
    if not result["ok"]:
        # start_resend_cycle already asked user
        return

    ensure_route_or_ask(ctx)
