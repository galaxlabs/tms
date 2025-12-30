from tms.utils.whatsapp_bot.context import build_context
from tms.utils.whatsapp_bot.handlers.text import handle_text
from tms.utils.whatsapp_bot.handlers.media import handle_media
from tms.utils.whatsapp_bot.handlers.resend import is_resend_active, handle_resend_media

def route_message(doc):
    ctx = build_context(doc)
    if not ctx:
        return

    ctype = (doc.content_type or "").lower()

    if ctype in ("image", "document"):
        if is_resend_active(ctx["contact"]):
            handle_resend_media(ctx)
        else:
            handle_media(ctx)
        return

    if ctype == "text":
        handle_text(ctx)
