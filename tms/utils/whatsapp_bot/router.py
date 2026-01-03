# # apps/tms/tms/utils/whatsapp_bot/router.py
# tms/utils/whatsapp_bot/router.py
import frappe
from tms.utils.whatsapp_bot.context import build_context
from tms.utils.whatsapp_bot.handlers.text import handle_text
from tms.utils.whatsapp_bot.handlers.media import handle_media


def route_message(doc):
    """
    Robust router:
      - If attach exists => ALWAYS treat as media (even if content_type == 'text' بسبب caption)
      - Otherwise route by content_type
    """
    ctx = build_context(doc)
    if not ctx:
        return

    ctype = (getattr(doc, "content_type", "") or "").lower().strip()
    attach = (getattr(doc, "attach", "") or "").strip()

    # ✅ MOST IMPORTANT FIX:
    # If there's an attachment URL, this is a media message (even if content_type is wrong).
    if attach:
        return handle_media(ctx)

    # Normal content-type based routing
    if ctype in ("image", "document", "file", "media"):
        return handle_media(ctx)

    # default -> text
    return handle_text(ctx)


# # apps/tms/tms/utils/whatsapp_bot/router.py
# import frappe
# from tms.utils.whatsapp_bot.context import build_context
# from tms.utils.whatsapp_bot.handlers.text import handle_text
# from tms.utils.whatsapp_bot.handlers.media import handle_media


# def route_message(doc):
#     """
#     Strict routing:
#       - image/document -> ONLY handle_media (even if caption exists)
#       - otherwise -> handle_text
#     """
#     ctx = build_context(doc)
#     if not ctx:
#         return

#     ctype = (getattr(doc, "content_type", "") or "").lower().strip()

#     # IMPORTANT: prevent caption causing text handler
#     if ctype in ("image", "document"):
#         return handle_media(ctx)

#     return handle_text(ctx)

# from tms.utils.whatsapp_bot.context import build_context
# from tms.utils.whatsapp_bot.handlers.text import handle_text
# from tms.utils.whatsapp_bot.handlers.media import handle_media
# from tms.utils.whatsapp_bot.handlers.resend import is_resend_active, handle_resend_media


# def route_message(doc):
#     ctx = build_context(doc)
#     if not ctx:
#         return

#     ctype = (doc.content_type or "").lower()

#     if ctype in ("image", "document"):
#         if is_resend_active(ctx["contact"]):
#             handle_resend_media(ctx)
#         else:
#             handle_media(ctx)
#         return

#     if ctype == "text":
#         handle_text(ctx)
#         return
