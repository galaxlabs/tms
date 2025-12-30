from tms.utils.whatsapp_bot.helpers.json_store import set_json
from tms.utils.whatsapp_bot.helpers.messaging import send_reply

def start_resend_cycle(incoming_doc, contact, lang: str, resend_indexes: list[int]):
    """
    Stores resend indexes on contact and asks for first resend.
    """
    set_json(contact, "resend_indexes_json", resend_indexes)
    contact.resend_ptr = 0
    contact.bot_state = "RESENDING_DOCS"
    contact.save(ignore_permissions=True)

    n = resend_indexes[0]
    send_reply(incoming_doc, "resend_document", lang,
               fallback="⚠️ Passenger #{n} document is not clear. Please resend passenger #{n}.",
               n=n)
