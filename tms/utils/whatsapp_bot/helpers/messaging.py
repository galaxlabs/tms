# tms/utils/whatsapp_bot/helpers/messaging.py
import frappe
from tms.utils.bot_settings import get_message
from tms.utils.whatsapp_utils import normalize_phone


def msg(key: str, lang: str, fallback: str = "", **kwargs) -> str:
    """
    Safe template fetcher:
    - reads from WhatsApp Bot Settings message_templates (via get_message)
    - formats with kwargs if placeholders exist
    - falls back to fallback (formatted) or key
    """
    text = (get_message(key, lang, **kwargs) or "").strip()
    if text:
        # get_message may already format; keep safe anyway
        try:
            return text.format(**kwargs)
        except Exception:
            return text

    if fallback:
        try:
            return fallback.format(**kwargs)
        except Exception:
            return fallback

    return key


def send_reply(incoming_doc, key: str, lang: str, fallback: str = "", **kwargs):
    """
    Threaded reply to an incoming WhatsApp Message.
    Creates an Outgoing WhatsApp Message with is_reply=1 and reply_to_message_id set.
    """
    if not incoming_doc:
        return None

    # Support doc.from or doc.from_
    to = normalize_phone(
        (getattr(incoming_doc, "from_", "") or getattr(incoming_doc, "from", "") or "").strip()
    )
    if not to:
        return None

    body = msg(key, lang, fallback=fallback, **kwargs)

    out = frappe.get_doc({
        "doctype": "WhatsApp Message",
        "type": "Outgoing",
        "to": to,
        "content_type": "text",
        "message": body,
        "message_type": "Manual",
        "is_reply": 1,
        "reply_to_message_id": getattr(incoming_doc, "message_id", None),
    })
    out.insert(ignore_permissions=True)

    try:
        out.reload()
        # try common method names (safe)
        if hasattr(out, "send"):
            out.send()
        elif hasattr(out, "send_message"):
            out.send_message()
        else:
            out.run_method("send")  # if controller defines it
    except Exception:
        frappe.log_error("WA SEND FAIL", frappe.get_traceback())

    

def send_plain(to: str, key: str, lang: str, fallback: str = "", **kwargs):
    """
    Non-threaded outgoing message to a WhatsApp ID/phone.
    """
    to = normalize_phone((to or "").strip())
    if not to:
        return None

    body = msg(key, lang, fallback=fallback, **kwargs)

    out = frappe.get_doc({
        "doctype": "WhatsApp Message",
        "type": "Outgoing",
        "to": to,
        "content_type": "text",
        "message": body,
        "message_type": "Manual",
    })
    out.insert(ignore_permissions=True)
    return out.name
