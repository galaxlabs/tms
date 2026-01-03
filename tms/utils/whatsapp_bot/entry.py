# tms/utils/whatsapp_bot/entry.py
# tms/utils/whatsapp_bot/entry.py
import frappe
from tms.utils.whatsapp_bot.router import route_message
from tms.utils.whatsapp_utils import normalize_phone


def already_replied(doc) -> bool:
    mid = getattr(doc, "message_id", None)
    if not mid:
        return False
    return bool(
        frappe.db.exists(
            "WhatsApp Message",
            {"type": "Outgoing", "is_reply": 1, "reply_to_message_id": mid},
        )
    )


def handle_incoming_whatsapp(doc, event=None):
    if getattr(doc, "type", None) != "Incoming":
        return

    doc.reload()
    ctype = (doc.content_type or "").lower().strip()

    # If media but attach not set yet, skip.
    # IMPORTANT: ensure this handler also runs on on_update so when attach arrives it will process.
    if ctype in ("image", "document"):
        if not (doc.attach or "").strip():
            return

    if already_replied(doc):
        return

    frappe.set_user("whatsapp.bot@example.com")

    sender_raw = doc.get("from") or doc.get("from_") or ""
    sender = normalize_phone(sender_raw) or sender_raw

    lock = frappe.cache().lock(f"wa_bot_lock:{sender}", timeout=30)
    if not lock.acquire(blocking=False):
        return

    try:
        route_message(doc)
    except Exception:
        frappe.log_error("WA BOT FAIL", frappe.get_traceback())
        raise
    finally:
        try:
            lock.release()
        except Exception:
            pass



# tms/utils/whatsapp_bot/entry.py
# import frappe
# from tms.utils.whatsapp_bot.router import route_message
# from tms.utils.whatsapp_utils import normalize_phone


# def _cache_key_done_for_doc(docname: str) -> str:
#     return f"wa_bot_done:doc:{docname}"


# def _cache_key_done_for_mid(mid: str) -> str:
#     return f"wa_bot_done:mid:{mid}"


# def already_processed(doc) -> bool:
#     """
#     Hard idempotency:
#     - If same WhatsApp Message doc processed already -> skip
#     - If same WhatsApp message_id processed already -> skip
#     """
#     docname = getattr(doc, "name", None)
#     mid = getattr(doc, "message_id", None)

#     # docname based (covers cases where message_id missing)
#     if docname:
#         k = _cache_key_done_for_doc(docname)
#         if frappe.cache().get_value(k):
#             return True

#     # message_id based (covers duplicate docs or retries)
#     if mid:
#         k2 = _cache_key_done_for_mid(mid)
#         if frappe.cache().get_value(k2):
#             return True

#     return False


# def mark_processed(doc):
#     """Mark as processed for 6 hours."""
#     docname = getattr(doc, "name", None)
#     mid = getattr(doc, "message_id", None)

#     if docname:
#         frappe.cache().set_value(_cache_key_done_for_doc(docname), 1, expires_in_sec=6 * 3600)
#     if mid:
#         frappe.cache().set_value(_cache_key_done_for_mid(mid), 1, expires_in_sec=6 * 3600)


# def already_replied(doc) -> bool:
#     """DB level dedup (optional if your outgoing rows are reliable)."""
#     mid = getattr(doc, "message_id", None)
#     if not mid:
#         return False
#     return bool(
#         frappe.db.exists(
#             "WhatsApp Message",
#             {"type": "Outgoing", "reply_to_message_id": mid},
#         )
#     )


# def handle_incoming_whatsapp(doc, event=None):
#     if getattr(doc, "type", None) != "Incoming":
#         return

#     # Reload to ensure attach/message fields are populated
#     doc.reload()
#     ctype = (doc.content_type or "").lower()

#     # Media must have attach (webhook sometimes inserts message first, attach later)
#     if ctype in ("image", "document"):
#         if not (doc.attach or "").strip():
#             return

#     # ✅ skip if already processed
#     if already_processed(doc):
#         return

#     # ✅ skip if already replied (optional)
#     if already_replied(doc):
#         mark_processed(doc)
#         return

#     frappe.set_user("whatsapp.bot@example.com")

#     sender_raw = doc.get("from") or doc.get("from_") or ""
#     sender = normalize_phone(sender_raw) or sender_raw

#     # Per-message lock (docname) - prevents simultaneous double runs
#     msg_lock = frappe.cache().lock(f"wa_bot_msg_lock:{doc.name}", timeout=60)
#     if not msg_lock.acquire(blocking=False):
#         return

#     # Per-sender lock - prevents concurrent messages from same sender
#     sender_lock = frappe.cache().lock(f"wa_bot_sender_lock:{sender}", timeout=30)
#     if not sender_lock.acquire(blocking=False):
#         try:
#             msg_lock.release()
#         except Exception:
#             pass
#         return

#     try:
#         # IMPORTANT: mark processed *before* heavy work to stop double triggers
#         mark_processed(doc)

#         route_message(doc)
#     except Exception:
#         frappe.log_error("WA BOT FAIL", frappe.get_traceback())
#         raise
#     finally:
#         try:
#             sender_lock.release()
#         except Exception:
#             pass
#         try:
#             msg_lock.release()
#         except Exception:
#             pass

# import frappe
# from tms.utils.whatsapp_bot.router import route_message
# from tms.utils.whatsapp_utils import normalize_phone


# def already_replied(doc) -> bool:
#     """DB level dedup (outgoing reply exists)."""
#     mid = getattr(doc, "message_id", None)
#     if not mid:
#         return False
#     return bool(
#         frappe.db.exists(
#             "WhatsApp Message",
#             {"type": "Outgoing", "reply_to_message_id": mid},
#         )
#     )


# def already_processed(doc) -> bool:
#     """
#     Hard idempotency: same incoming message_id should not be processed twice.
#     WhatsApp webhook can retry same payload.
#     """
#     mid = getattr(doc, "message_id", None)
#     if not mid:
#         return False

#     key = f"wa_bot_done:{mid}"
#     if frappe.cache().get_value(key):
#         return True

#     # Mark processed for few hours
#     frappe.cache().set_value(key, 1, expires_in_sec=6 * 3600)
#     return False


# def handle_incoming_whatsapp(doc, event=None):
#     if getattr(doc, "type", None) != "Incoming":
#         return

#     # Reload to ensure attach/message fields are populated
#     doc.reload()
#     ctype = (doc.content_type or "").lower()

#     # Media must have attach (webhook sometimes inserts message first, attach later)
#     if ctype in ("image", "document"):
#         if not (doc.attach or "").strip():
#             return

#     # ✅ incoming idempotency first
#     if already_processed(doc):
#         return

#     # ✅ DB reply dedup
#     if already_replied(doc):
#         return

#     frappe.set_user("whatsapp.bot@example.com")

#     sender_raw = doc.get("from") or doc.get("from_") or ""
#     sender = normalize_phone(sender_raw) or sender_raw

#     # Per-sender lock to prevent concurrent processing
#     lock = frappe.cache().lock(f"wa_bot_lock:{sender}", timeout=30)
#     if not lock.acquire(blocking=False):
#         return

#     try:
#         route_message(doc)
#     except Exception:
#         frappe.log_error("WA BOT FAIL", frappe.get_traceback())
#         raise
#     finally:
#         try:
#             lock.release()
#         except Exception:
#             pass


# # tms/utils/whatsapp_bot/entry.py
# import frappe
# from tms.utils.whatsapp_bot.router import route_message
# from tms.utils.whatsapp_utils import normalize_phone


# def already_replied(doc) -> bool:
#     mid = getattr(doc, "message_id", None)
#     if not mid:
#         return False
#     return bool(
#         frappe.db.exists(
#             "WhatsApp Message",
#             {"type": "Outgoing", "reply_to_message_id": mid},
#         )
#     )


# def handle_incoming_whatsapp(doc, event=None):
#     if getattr(doc, "type", None) != "Incoming":
#         return

#     # Reload to ensure attach/message fields are populated
#     doc.reload()
#     ctype = (doc.content_type or "").lower()

#     # Media must have attach (webhook sometimes inserts message first, attach later)
#     if ctype in ("image", "document"):
#         if not (doc.attach or "").strip():
#             return

#     # Dedup: if we've already replied to this message id, skip
#     if already_replied(doc):
#         return

#     frappe.set_user("whatsapp.bot@example.com")

#     sender_raw = doc.get("from") or doc.get("from_") or ""
#     sender = normalize_phone(sender_raw) or sender_raw

#     # Per-sender lock to prevent concurrent processing (webhook retries / multiple workers)
#     lock = frappe.cache().lock(f"wa_bot_lock:{sender}", timeout=30)

#     if not lock.acquire(blocking=False):
#         return

#     try:
#         route_message(doc)
#     except Exception:
#         frappe.log_error("WA BOT FAIL", frappe.get_traceback())
#         raise
#     finally:
#         try:
#             lock.release()
#         except Exception:
#             pass
