# tms/utils/whatsapp_bot/context.py
import frappe
from frappe.utils import now_datetime, add_to_date
from tms.utils.bot_settings import get_settings, normalize_lang
from tms.utils.whatsapp_utils import normalize_phone, get_or_create_contact
from tms.utils.whatsapp_bot.flows.trip_flow import get_or_create_trip
from tms.utils.whatsapp_bot.helpers.messaging import send_reply

def build_context(doc):
    settings, _ = get_settings()
    if not int(settings.enabled or 0):
        return None

    lang = normalize_lang(settings.default_language)

    sender = normalize_phone(doc.get("from") or doc.get("from_") or "")
    contact = get_or_create_contact(sender, doc.profile_name or "")
    if not contact:
        return None

    # update conversation window
    now = now_datetime()
    hours = int(settings.conversation_hours or 24)
    contact.last_inbound_at = now
    contact.conversation_expires_at = add_to_date(now, hours=hours)
    contact.save(ignore_permissions=True)

    # driver validation
    driver = frappe.db.get_value("Staff", {"mobile_no": ["like", f"%{sender[-9:]}"]}, "name")
    if not driver:
        send_reply(doc, "not_registered_driver", lang)
        return None

    trip = get_or_create_trip(driver, contact)

    return {
        "doc": doc,
        "settings": settings,
        "lang": lang,
        "contact": contact,
        "driver": driver,
        "trip": trip,
    }
