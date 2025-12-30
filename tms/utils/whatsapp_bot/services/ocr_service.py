from tms.utils.passenger_ocr_service import process_passenger_images_batch
from tms.utils.whatsapp_bot.helpers.json_store import get_json
from tms.utils.whatsapp_bot.flows.resend_flow import start_resend_cycle

def run_batch_ocr(ctx):
    trip = ctx["trip"]
    doc = ctx["doc"]
    contact = ctx["contact"]
    lang = ctx["lang"]

    urls = get_json(contact, "collected_file_urls_json", [])

    result = process_passenger_images_batch(
        trip_name=trip.name,
        file_urls=urls,
        waba_message=doc.name,
    )

    if not result.get("ok"):
        resend = result.get("resend_indexes") or []
        if resend:
            start_resend_cycle(doc, contact, lang, resend)
        return {"ok": False, "resend_indexes": resend}

    return {"ok": True, "resend_indexes": []}
