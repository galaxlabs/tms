import frappe
from frappe.utils import now_datetime, add_to_date

from tms.utils.bot_settings import get_settings, normalize_lang
from tms.utils.whatsapp_utils import normalize_phone, get_or_create_contact
from tms.utils.whatsapp_bot.helpers.messaging import send_reply


def build_context(doc):
    """
    Returns a dict context used by router/handlers:
    {
      "doc", "settings", "lang", "contact", "driver", "driver_name", "trip", "sender_no"
    }
    """
    settings, _ = get_settings()
    if not int(settings.enabled or 0):
        return None

    lang = normalize_lang(settings.default_language)

    sender = normalize_phone(getattr(doc, "from", None) or getattr(doc, "from_", None) or doc.get("from") or doc.get("from_") or "")
    profile_name = (getattr(doc, "profile_name", None) or "").strip()

    contact = get_or_create_contact(sender, profile_name)
    if not contact:
        return None

    # --- keep display_name updated (so we can call unregistered people by name) ---
    # WhatsApp Contact has "display_name"
    if profile_name and (not getattr(contact, "display_name", None) or contact.display_name.strip() != profile_name):
        frappe.db.set_value(contact.doctype, contact.name, "display_name", profile_name, update_modified=False)
        contact.display_name = profile_name

    # update conversation window (single UPDATE)
    now = now_datetime()
    hours = int(settings.conversation_hours or 24)
    expires = add_to_date(now, hours=hours)

    updates = {
        "last_inbound_at": now,
        "conversation_expires_at": expires,
    }
    frappe.db.set_value(contact.doctype, contact.name, updates, update_modified=False)
    contact.last_inbound_at = now
    contact.conversation_expires_at = expires

    # ---- driver lookup (get Staff name + full_name) ----
    driver_row = frappe.db.get_value(
        "Staff",
        {"mobile_no": ["like", f"%{sender[-9:]}"]},
        ["name", "full_name"],
        as_dict=True,
    )

    # ✅ NOT REGISTERED: reply with WhatsApp name (profile_name) OR contact.display_name OR phone fallback
    if not driver_row:
        display = (
            profile_name
            or (getattr(contact, "display_name", None) or "").strip()
            or sender
            or "there"
        )

        # use a named template (you create in WhatsApp Bot Settings.message_templates)
        send_reply(
            doc,
            "not_registered_staff_named",
            lang,
            fallback="⚠️ Hi {name}, you are not registered as staff in this company and can’t use this bot.",
            name=display,
        )
        return None

    driver_id = driver_row.get("name")
    driver_full_name = (driver_row.get("full_name") or "").strip()

    # fallback if Staff.full_name empty
    if not driver_full_name:
        driver_full_name = profile_name or driver_id

    # ✅ store Staff on contact (useful for future fast checks / reports)
    if getattr(contact, "staff", None) != driver_id:
        frappe.db.set_value(contact.doctype, contact.name, "staff", driver_id, update_modified=False)
        contact.staff = driver_id

    trip = None
    if getattr(contact, "current_trip", None) and frappe.db.exists("Trip", contact.current_trip):
        trip = frappe.get_doc("Trip", contact.current_trip)

    return {
        "doc": doc,
        "settings": settings,
        "lang": lang,
        "contact": contact,
        "driver": driver_id,               # Staff docname (id)
        "driver_name": driver_full_name,   # Staff.full_name (display name)
        "trip": trip,
        "sender_no": sender,
    }

# tms/utils/whatsapp_bot/context.py
# import frappe
# from frappe.utils import now_datetime, add_to_date

# from tms.utils.bot_settings import get_settings, normalize_lang
# from tms.utils.whatsapp_utils import normalize_phone, get_or_create_contact
# from tms.utils.whatsapp_bot.helpers.messaging import send_reply


# def build_context(doc):
#     """
#     Returns a dict context used by router/handlers:
#     {
#       "doc", "settings", "lang", "contact", "driver", "driver_name", "trip"
#     }
#     """
#     settings, _ = get_settings()
#     if not int(settings.enabled or 0):
#         return None

#     lang = normalize_lang(settings.default_language)

#     sender = normalize_phone(doc.get("from") or doc.get("from_") or "")
#     contact = get_or_create_contact(sender, doc.profile_name or "")
#     if not contact:
#         return None

#     # update conversation window (single UPDATE)
#     now = now_datetime()
#     hours = int(settings.conversation_hours or 24)
#     expires = add_to_date(now, hours=hours)

#     updates = {
#         "last_inbound_at": now,
#         "conversation_expires_at": expires,
#     }
#     frappe.db.set_value(contact.doctype, contact.name, updates, update_modified=False)

#     # keep in-memory doc in sync
#     contact.last_inbound_at = now
#     contact.conversation_expires_at = expires

#     # ---- driver lookup (get name + full_name) ----
#     driver_row = frappe.db.get_value(
#         "Staff",
#         {"mobile_no": ["like", f"%{sender[-9:]}"]},
#         ["name", "full_name"],
#         as_dict=True,
#     )

#     if not driver_row:
#         send_reply(doc, "not_registered_driver", lang)
#         return None

#     driver_id = driver_row.get("name")
#     driver_full_name = (driver_row.get("full_name") or "").strip()

#     # fallback if full_name empty
#     if not driver_full_name:
#         driver_full_name = (doc.profile_name or "").strip() or driver_id

#     trip = None
#     if getattr(contact, "current_trip", None) and frappe.db.exists("Trip", contact.current_trip):
#         trip = frappe.get_doc("Trip", contact.current_trip)

#     return {
#         "doc": doc,
#         "settings": settings,
#         "lang": lang,
#         "contact": contact,
#         "driver": driver_id,              # Staff docname (id)
#         "driver_name": driver_full_name,  # Staff.full_name (display name)
#         "trip": trip,
#     }
# ----------------------------------------------------------------------
# # tms/utils/whatsapp_bot/context.py
# import frappe
# from frappe.utils import now_datetime, add_to_date

# from tms.utils.bot_settings import get_settings, normalize_lang
# from tms.utils.whatsapp_utils import normalize_phone, get_or_create_contact
# from tms.utils.whatsapp_bot.helpers.messaging import send_reply


# def build_context(doc):
#     settings, _ = get_settings()
#     if not int(settings.enabled or 0):
#         return None

#     lang = normalize_lang(settings.default_language)

#     sender = normalize_phone(doc.get("from") or doc.get("from_") or "")
#     contact = get_or_create_contact(sender, doc.profile_name or "")
#     if not contact:
#         return None

#     now = now_datetime()
#     hours = int(settings.conversation_hours or 24)
#     expires = add_to_date(now, hours=hours)

#     frappe.db.set_value(
#         contact.doctype,
#         contact.name,
#         {"last_inbound_at": now, "conversation_expires_at": expires},
#         update_modified=False,
#     )

#     contact.last_inbound_at = now
#     contact.conversation_expires_at = expires

#     driver = frappe.db.get_value("Staff", {"mobile_no": ["like", f"%{sender[-9:]}"]}, "name")
#     if not driver:
#         send_reply(doc, "not_registered_driver", lang)
#         return None

#     trip = None
#     if contact.current_trip and frappe.db.exists("Trip", contact.current_trip):
#         trip = frappe.get_doc("Trip", contact.current_trip)

#     return {"doc": doc, "settings": settings, "lang": lang, "contact": contact, "driver": driver, "trip": trip}
