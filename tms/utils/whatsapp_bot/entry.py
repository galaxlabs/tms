# tms/utils/whatsapp_bot/entry.py
import frappe
from tms.utils.whatsapp_bot.router import route_message

def handle_incoming_whatsapp(doc, event=None):
    # IMPORTANT: prevent bot from running on Outgoing messages
    if getattr(doc, "type", None) != "Incoming":
        return

    # optional: ignore if content_type empty
    if not getattr(doc, "content_type", None):
        return

    frappe.set_user("whatsapp.bot@example.com")
    route_message(doc)
