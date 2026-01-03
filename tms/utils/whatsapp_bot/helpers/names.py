# apps/tms/tms/utils/whatsapp_bot/helpers/names.py

import frappe

def resolve_display_name(ctx) -> str:
    """
    Priority:
    1) Staff full_name (if registered driver/staff)
    2) Trip driver name (if you store it somewhere)
    3) WhatsApp profile name from webhook/doc
    4) Contact name or phone fallback
    """
    driver = ctx.get("driver")  # usually Staff name if matched
    contact = ctx.get("contact")
    doc = ctx.get("doc")

    # 1) Staff full_name
    if driver and frappe.db.exists("Staff", driver):
        full = frappe.db.get_value("Staff", driver, "full_name")
        if full:
            return full

    # 2) Trip driver name fallback (optional)
    trip = ctx.get("trip")
    if trip:
        dn = getattr(trip, "driver_name", None) or getattr(trip, "driver", None)
        if dn:
            return str(dn)

    # 3) WhatsApp profile name (from webhook / WhatsApp Message doc)
    wa_name = getattr(doc, "sender_name", None) or getattr(doc, "profile_name", None)
    if wa_name:
        return str(wa_name)

    # 4) Contact or phone
    if contact:
        return getattr(contact, "full_name", None) or getattr(contact, "first_name", None) or contact.name

    sender_no = ctx.get("sender_no") or getattr(doc, "from_number", None)
    return sender_no or "there"
