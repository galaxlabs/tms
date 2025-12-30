from tms.utils.whatsapp_bot.helpers.json_store import get_json, set_json
from tms.utils.whatsapp_bot.helpers.messaging import send_reply
from tms.utils.whatsapp_bot.services.ocr_service import run_batch_ocr
from tms.utils.whatsapp_bot.flows.route_flow import ensure_route_or_ask
from tms.utils.whatsapp_bot.flows.passenger_flow import write_passengers_and_finalize

def handle_media(ctx):
    contact = ctx["contact"]
    trip = ctx["trip"]
    doc = ctx["doc"]
    lang = ctx["lang"]

    file_url = doc.attach
    if not file_url:
        send_reply(doc, "no_attachment", lang)
        return

    urls = get_json(contact, "collected_file_urls_json", [])
    urls.append(file_url)
    set_json(contact, "collected_file_urls_json", urls)

    received = len(urls)
    expected = int(contact.expected_passengers or 0)

    contact.received_images = received
    contact.save(ignore_permissions=True)

    if expected <= 0:
        send_reply(doc, "doc_received_ask_count", lang, received=received)
        return

    if received < expected:
        send_reply(doc, "doc_progress", lang,
                   received=received, expected=expected,
                   remaining=expected - received)
        return

    # 🔥 Trigger OCR
    result = run_batch_ocr(trip, urls, doc)

    if not result["ok"]:
        return  # resend flow will handle messaging

    # OCR OK → route → passengers → finalize
    ensure_route_or_ask(ctx)
