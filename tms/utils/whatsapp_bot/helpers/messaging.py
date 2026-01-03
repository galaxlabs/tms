# # tms/utils/whatsapp_bot/helpers/messaging.py
import frappe
from tms.utils.bot_settings import get_settings, normalize_lang
from tms.utils.whatsapp_bot.helpers.names import resolve_display_name

# ------------------------------------------------------------
# Tri-lingual output (EN + UR + AR in ONE message)
# ------------------------------------------------------------
DEFAULT_LANGS = ("en", "ur", "ar")

LANG_LABEL = {
    "en": "🇬🇧 English",
    "ur": "🇵🇰 اردو",
    "ar": "🇸🇦 العربية",
}

SEPARATOR = "\n\n— — —\n\n"


def _safe_format(tpl: str, **kwargs) -> str:
    """Never crash on bad templates / missing keys."""
    if not tpl:
        return ""
    try:
        return tpl.format(**kwargs)
    except Exception:
        return tpl


# def _resolve_template(templates: dict, key: str, lang: str) -> str | None:
#     """
#     Supports common JSON shapes:

#     A) templates = { "en": {key:"..."}, "ur": {...}, "ar": {...} }
#     B) templates = { key: {"en":"...", "ur":"...", "ar":"..."} }
#     C) templates = { key: "..." }  (single text)
#     """
#     if not templates or not isinstance(templates, dict):
#         return None

#     # A) root by language
#     if lang in templates and isinstance(templates.get(lang), dict):
#         v = templates.get(lang, {}).get(key)
#         if isinstance(v, str) and v.strip():
#             return v

#     # B/C) root by key
#     if key in templates:
#         v = templates.get(key)

#         if isinstance(v, dict):
#             vv = v.get(lang)
#             if isinstance(vv, str) and vv.strip():
#                 return vv
#             # fallback to en if exists
#             vv2 = v.get("en")
#             if isinstance(vv2, str) and vv2.strip():
#                 return vv2

#         if isinstance(v, str) and v.strip():
#             return v

#     return None
def _resolve_template(templates: dict, key: str, lang: str) -> str | None:
    if not templates or not isinstance(templates, dict):
        return None

    # A) root by language
    if lang in templates and isinstance(templates.get(lang), dict):
        v = templates.get(lang, {}).get(key)
        if isinstance(v, str) and v.strip():
            return v

    # B/C) root by key
    if key in templates:
        v = templates.get(key)

        if isinstance(v, dict):
            vv = v.get(lang)
            if isinstance(vv, str) and vv.strip():
                return vv
            # ❌ DO NOT fallback to "en" here in tri-lang mode
            return None

        if isinstance(v, str) and v.strip():
            return v

    return None


def _fallback_for_lang(fallback, lang: str) -> str:
    """
    fallback can be:
      - None
      - str
      - dict: {"en":"..","ur":"..","ar":".."}  (recommended)
    """
    if not fallback:
        return ""
    if isinstance(fallback, dict):
        v = fallback.get(lang) or fallback.get("en") or ""
        return v if isinstance(v, str) else ""
    if isinstance(fallback, str):
        return fallback
    return ""


def _tri_lang_enabled() -> bool:
    """
    Optional checkbox in WhatsApp Bot Settings: send_all_languages (Check)
    If field doesn't exist -> default True
    """
    try:
        settings, _ = get_settings()
        if settings and hasattr(settings, "send_all_languages"):
            return bool(int(getattr(settings, "send_all_languages") or 0))
    except Exception:
        pass
    return True


def _default_greet_tpl(lang: str) -> str:
    if lang == "ar":
        return "مرحباً {name} 👋"
    if lang == "ur":
        return "السلام علیکم {name} 👋"
    return "Hi {name} 👋"


def _greet_for_lang(templates: dict, lang: str, name: str) -> str:
    # allow greet_prefix in settings templates
    tpl = _resolve_template(templates, "greet_prefix", lang)
    if not tpl:
        tpl = _default_greet_tpl(lang)
    return _safe_format(tpl, name=name).strip()


def _build_message(key: str, lang: str | None, fallback=None, **kwargs) -> str:
    settings, templates = get_settings()

    # normalize_lang may accept English/Arabic/Urdu etc.
    chosen_lang = normalize_lang(lang or getattr(settings, "default_language", "en"))

    # ---- name + greet injection (works for all templates) ----
    ctx = kwargs.get("ctx") or {}
    name = kwargs.get("name") or resolve_display_name(ctx) or "there"

    if _tri_lang_enabled():
        parts = []
        for lg in DEFAULT_LANGS:
            tpl = _resolve_template(templates, key, lg)
            if not tpl:
                tpl = _fallback_for_lang(fallback, lg)

            greet = _greet_for_lang(templates, lg, name)

            # inject vars
            safe_vars = {
                "name": name,
                "greet": greet,
                **kwargs,
            }

            text = _safe_format(tpl, **safe_vars).strip()
            if not text:
                continue

            parts.append(f"{LANG_LABEL.get(lg, lg)}\n{text}")

        if parts:
            return SEPARATOR.join(parts)

        # If no templates found at all, try fallback raw
        greet = _greet_for_lang(templates, "en", name)
        raw = _safe_format(_fallback_for_lang(fallback, "en"), name=name, greet=greet, **kwargs).strip()
        return raw or "…"

    # Single-language mode (if you ever disable it)
    tpl = _resolve_template(templates, key, chosen_lang)
    if not tpl:
        tpl = _fallback_for_lang(fallback, chosen_lang)

    greet = _greet_for_lang(templates, chosen_lang, name)

    return _safe_format(
        tpl,
        name=name,
        greet=greet,
        **kwargs,
    ).strip() or "…"


def _send_outgoing_reply(in_doc, message_text: str):
    """
    Creates an Outgoing WhatsApp Message reply.
    Outgoing, is_reply=1, reply_to_message_id = inbound.message_id
    """
    to_number = in_doc.get("from") or in_doc.get("from_") or ""
    reply_mid = getattr(in_doc, "message_id", None)

    out = frappe.get_doc(
        {
            "doctype": "WhatsApp Message",
            "type": "Outgoing",
            "content_type": "text",
            "message": message_text,
            "to": to_number,
            "is_reply": 1,
            "reply_to_message_id": reply_mid,
        }
    )
    out.insert(ignore_permissions=True)
    return out.name


def send_reply(doc, key, lang=None, fallback=None, **kwargs):
    """
    Main helper used by bot.

    Supports:
      - tri-language output
      - {name} and {greet} placeholders automatically
      - safe formatting

    Best practice:
      send_reply(doc, "ask_passenger_count", lang, ctx=ctx)
      send_reply(doc, "doc_progress", lang, ctx=ctx, received=1, expected=3, remaining=2)
    """
    msg = _build_message(key, lang, fallback=fallback, **kwargs)
    return _send_outgoing_reply(doc, msg)

# apps/tms/tms/utils/whatsapp_bot/helpers/messaging.py
# import frappe
# from tms.utils.bot_settings import get_settings, normalize_lang
# from tms.utils.whatsapp_bot.helpers.names import resolve_display_name


# # ------------------------------------------------------------
# # Tri-lingual output (EN + UR + AR in ONE message)
# # ------------------------------------------------------------
# DEFAULT_LANGS = ("en", "ur", "ar")

# LANG_LABEL = {
#     "en": "🇬🇧 English",
#     "ur": "🇵🇰 اردو",
#     "ar": "🇸🇦 العربية",
# }

# SEPARATOR = "\n\n— — —\n\n"


# def _safe_format(tpl: str, **kwargs) -> str:
#     """Never crash on bad templates / missing keys."""
#     if not tpl:
#         return ""
#     try:
#         return tpl.format(**kwargs)
#     except Exception:
#         return tpl


# def _resolve_template(templates: dict, key: str, lang: str) -> str | None:
#     """
#     Supports common JSON shapes:

#     A) templates = { "en": {key:"..."}, "ur": {...}, "ar": {...} }
#     B) templates = { key: {"en":"...", "ur":"...", "ar":"..."} }
#     C) templates = { key: "..." }  (single text)
#     """
#     if not templates or not isinstance(templates, dict):
#         return None

#     # A) root by language
#     if lang in templates and isinstance(templates.get(lang), dict):
#         v = templates.get(lang, {}).get(key)
#         if isinstance(v, str) and v.strip():
#             return v

#     # B/C) root by key
#     if key in templates:
#         v = templates.get(key)

#         if isinstance(v, dict):
#             vv = v.get(lang)
#             if isinstance(vv, str) and vv.strip():
#                 return vv
#             # fallback to en if exists
#             vv2 = v.get("en")
#             if isinstance(vv2, str) and vv2.strip():
#                 return vv2

#         if isinstance(v, str) and v.strip():
#             return v

#     return None


# def _fallback_for_lang(fallback, lang: str) -> str:
#     """
#     fallback can be:
#       - None
#       - str
#       - dict: {"en":"..","ur":"..","ar":".."}  (recommended)
#     """
#     if not fallback:
#         return ""
#     if isinstance(fallback, dict):
#         v = fallback.get(lang) or fallback.get("en") or ""
#         return v if isinstance(v, str) else ""
#     if isinstance(fallback, str):
#         return fallback
#     return ""


# def _tri_lang_enabled() -> bool:
#     """
#     Optional checkbox in WhatsApp Bot Settings: send_all_languages (Check)
#     If field doesn't exist -> default True (as you requested).
#     """
#     try:
#         settings, _ = get_settings()
#         if settings and hasattr(settings, "send_all_languages"):
#             return bool(int(getattr(settings, "send_all_languages") or 0))
#     except Exception:
#         pass
#     return True


# def _build_message(key: str, lang: str | None, fallback=None, **kwargs) -> str:
#     settings, templates = get_settings()
#     # normalize_lang may accept English/Arabic/Urdu etc.
#     _ = normalize_lang(lang or getattr(settings, "default_language", "en"))

#     if _tri_lang_enabled():
#         parts = []
#         for lg in DEFAULT_LANGS:
#             tpl = _resolve_template(templates, key, lg)
#             if not tpl:
#                 tpl = _fallback_for_lang(fallback, lg)

#             text = _safe_format(tpl, **kwargs).strip()
#             if not text:
#                 continue

#             parts.append(f"{LANG_LABEL.get(lg, lg)}\n{text}")

#         if parts:
#             return SEPARATOR.join(parts)

#         # If no templates found at all, try fallback raw
#         raw = _safe_format(_fallback_for_lang(fallback, "en"), **kwargs).strip()
#         return raw or "…"

#     # Single-language mode (if you ever disable it)
#     chosen = normalize_lang(lang or getattr(settings, "default_language", "en"))
#     tpl = _resolve_template(templates, key, chosen)
#     if not tpl:
#         tpl = _fallback_for_lang(fallback, chosen)
#     return _safe_format(tpl, **kwargs).strip() or "…"


# def _send_outgoing_reply(in_doc, message_text: str):
#     """
#     Creates an Outgoing WhatsApp Message reply.
#     This matches your dedup:
#       Outgoing, is_reply=1, reply_to_message_id = inbound.message_id
#     """
#     to_number = in_doc.get("from") or in_doc.get("from_") or ""
#     reply_mid = getattr(in_doc, "message_id", None)

#     out = frappe.get_doc(
#         {
#             "doctype": "WhatsApp Message",
#             "type": "Outgoing",
#             "content_type": "text",
#             "message": message_text,
#             "to": to_number,
#             "is_reply": 1,
#             "reply_to_message_id": reply_mid,
#         }
#     )
#     out.insert(ignore_permissions=True)
#     return out.name


# def send_reply(doc, key, lang, fallback="", **kwargs):
#     settings = frappe.get_single("WhatsApp Bot Settings")
#     templates = _load_templates(settings)  # your existing loader

#     name = kwargs.pop("name", None) or resolve_display_name(kwargs.get("ctx") or {})
#     greet_tpl = (templates.get("greet_prefix") or {}).get(lang) \
#                or (templates.get("greet_prefix") or {}).get("en") \
#                or "Hi {name}"

#     greet = greet_tpl.format(name=name)

#     tpl = (templates.get(key) or {}).get(lang) \
#           or (templates.get(key) or {}).get("en") \
#           or fallback

#     # inject dynamic vars
#     safe_vars = {"name": name, "greet": greet, **kwargs}

#     try:
#         msg = tpl.format(**safe_vars)
#     except Exception:
#         # fail-safe if template has missing placeholders
#         msg = tpl

#     _send_whatsapp(doc, msg)  # your existing sender


# def send_reply(doc, key: str, lang: str | None = None, fallback=None, **kwargs):
#     """
#     Your bot calls this everywhere.

#     New behavior:
#       - Sends ONE message that contains EN + UR + AR sections (default ON)
#       - Accepts fallback as str OR dict {"en": "...", "ur": "...", "ar": "..."}
#     """
#     try:
#         msg = _build_message(key, lang, fallback=fallback, **kwargs)
#         if msg:
#             _send_outgoing_reply(doc, msg)
#     except Exception:
#         frappe.log_error("WA SEND_REPLY FAIL", frappe.get_traceback())
#         return

# apps/tms/tms/utils/whatsapp_bot/helpers/messaging.py
# import frappe
# from tms.utils.bot_settings import get_settings

# # ------------------------------------------------------------
# # Multi-language output (EN + UR + AR in ONE message)
# # ------------------------------------------------------------
# DEFAULT_LANGS = ("en", "ur", "ar")

# LANG_LABEL = {
#     "en": "🇬🇧 English",
#     "ur": "🇵🇰 اردو",
#     "ar": "🇸🇦 العربية",
# }


# def _render_template(tpl: str, **kwargs) -> str:
#     """Safe format for templates like 'Hello {name}'."""
#     if not tpl:
#         return ""
#     try:
#         return tpl.format(**kwargs)
#     except Exception:
#         # if placeholders mismatch, return raw template (never crash)
#         return tpl


# def _resolve_message_from_meta(messages_meta, key: str, lang: str) -> str | None:
#     """
#     Try to resolve message template from whatever structure get_settings() returns.
#     We support multiple common shapes:

#     A) messages_meta = { "en": {key: "..."}, "ur": {...}, "ar": {...} }
#     B) messages_meta = { key: {"en": "...", "ur": "...", "ar": "..."} }
#     C) messages_meta = { key: "..." }  (single)
#     """
#     if not messages_meta:
#         return None

#     # A) by-lang root
#     if isinstance(messages_meta, dict) and lang in messages_meta and isinstance(messages_meta.get(lang), dict):
#         v = messages_meta.get(lang, {}).get(key)
#         if isinstance(v, str) and v.strip():
#             return v

#     # B) by-key root
#     if isinstance(messages_meta, dict) and key in messages_meta:
#         v = messages_meta.get(key)

#         if isinstance(v, dict):
#             vv = v.get(lang)
#             if isinstance(vv, str) and vv.strip():
#                 return vv

#         if isinstance(v, str) and v.strip():
#             return v

#     return None


# def _get_template(key: str, lang: str, fallback: str | None = None) -> str:
#     """
#     Pull template from bot settings messages mapping if available,
#     otherwise return fallback.
#     """
#     settings, messages_meta = get_settings()

#     tpl = _resolve_message_from_meta(messages_meta, key, lang)

#     # If settings doc has any direct fields for message keys (rare), try it too:
#     if not tpl and settings and hasattr(settings, key):
#         val = getattr(settings, key)
#         if isinstance(val, str) and val.strip():
#             tpl = val

#     if tpl and tpl.strip():
#         return tpl

#     return fallback or ""


# def _is_trilingual_enabled() -> bool:
#     """
#     Optional setting: add a Checkbox field `send_all_languages`
#     in your Bot Settings doctype.
#     If field doesn't exist, we default to ON (True) as you requested.
#     """
#     try:
#         settings, _ = get_settings()
#         if settings and hasattr(settings, "send_all_languages"):
#             return bool(int(getattr(settings, "send_all_languages") or 0))
#     except Exception:
#         pass

#     # default ON
#     return True


# def _build_trilingual_message(key: str, fallback: str | None = None, **kwargs) -> str:
#     """
#     Build ONE message containing EN + UR + AR (if available).
#     """
#     parts = []
#     for lg in DEFAULT_LANGS:
#         tpl = _get_template(key, lg, fallback=fallback)
#         text = _render_template(tpl, **kwargs).strip()
#         if not text:
#             continue

#         label = LANG_LABEL.get(lg, lg)
#         parts.append(f"{label}\n{text}")

#     # If nothing resolved at all, at least send fallback raw
#     if not parts:
#         raw = _render_template(fallback or "", **kwargs).strip()
#         return raw or "…"

#     return "\n\n— — —\n\n".join(parts)


# def _send_outgoing_reply(in_doc, message_text: str):
#     """
#     Send reply in the same way your system already does:
#     Create an Outgoing WhatsApp Message row (queued by your WA sender).
#     This matches your dedup logic:
#       Outgoing, is_reply=1, reply_to_message_id = inbound.message_id
#     """
#     to_number = in_doc.get("from") or in_doc.get("from_") or ""
#     reply_mid = getattr(in_doc, "message_id", None)

#     out = frappe.get_doc(
#         {
#             "doctype": "WhatsApp Message",
#             "type": "Outgoing",
#             "content_type": "text",
#             "message": message_text,
#             "to": to_number,
#             "is_reply": 1,
#             "reply_to_message_id": reply_mid,
#         }
#     )
#     out.insert(ignore_permissions=True)
#     return out.name


# def send_reply(doc, key: str, lang: str | None = None, fallback: str | None = None, **kwargs):
#     """
#     Main helper used everywhere in bot.

#     NEW behavior (your request):
#       - If trilingual enabled -> send one message containing EN+UR+AR
#       - Otherwise -> send single language message (based on lang)

#     NOTE:
#       - We do not crash if templates missing.
#       - We always try to use settings/messages first; fallback is used if missing.
#     """
#     try:
#         if _is_trilingual_enabled():
#             msg = _build_trilingual_message(key, fallback=fallback, **kwargs)
#             _send_outgoing_reply(doc, msg)
#             return

#         # single language mode (old behavior)
#         lg = (lang or "en").strip().lower()
#         tpl = _get_template(key, lg, fallback=fallback)
#         msg = _render_template(tpl, **kwargs).strip() or (fallback or "")
#         if msg:
#             _send_outgoing_reply(doc, msg)

#     except Exception:
#         frappe.log_error("WA SEND_REPLY FAIL", frappe.get_traceback())
#         # never raise from messaging helper
#         return

# import frappe
# from tms.utils.bot_settings import get_message
# from tms.utils.whatsapp_utils import normalize_phone


# def msg(key: str, lang: str, fallback: str = "", **kwargs) -> str:
#     """
#     Resolve a message template key into final text.
#     Priority:
#       1) WhatsApp Bot Settings template (get_message)
#       2) fallback (formatted)
#       3) key itself
#     """
#     text = (get_message(key, lang, **kwargs) or "").strip()
#     if text:
#         try:
#             return text.format(**kwargs)
#         except Exception:
#             return text

#     if fallback:
#         try:
#             return fallback.format(**kwargs)
#         except Exception:
#             return fallback

#     return key


# def _safe_send(out_doc):
#     """
#     Try to send the Outgoing WhatsApp Message using whatever controller method exists.
#     Never raise (webhook should not crash because send failed).
#     """
#     try:
#         out_doc.reload()
#         if hasattr(out_doc, "send"):
#             out_doc.send()
#         elif hasattr(out_doc, "send_message"):
#             out_doc.send_message()
#         else:
#             out_doc.run_method("send")
#     except Exception:
#         frappe.log_error("WA SEND FAIL", frappe.get_traceback())


# def send_reply(incoming_doc, key: str, lang: str, fallback: str = "", **kwargs):
#     """
#     Threaded reply to an incoming WhatsApp Message.
#     Creates an Outgoing WhatsApp Message with:
#       - is_reply = 1
#       - reply_to_message_id = incoming.message_id
#     """
#     if not incoming_doc:
#         return None

#     # Support doc.from_ or doc.from
#     to = normalize_phone(
#         (getattr(incoming_doc, "from_", "") or getattr(incoming_doc, "from", "") or "").strip()
#     )
#     if not to:
#         return None

#     body = msg(key, lang, fallback=fallback, **kwargs)

#     out = frappe.get_doc(
#         {
#             "doctype": "WhatsApp Message",
#             "type": "Outgoing",
#             "to": to,
#             "content_type": "text",
#             "message": body,
#             "message_type": "Manual",
#             "is_reply": 1,
#             "reply_to_message_id": getattr(incoming_doc, "message_id", None),
#         }
#     )

#     out.insert(ignore_permissions=True)
#     _safe_send(out)
#     return out.name


# def send_plain(to: str, key: str, lang: str, fallback: str = "", **kwargs):
#     """
#     Non-threaded outgoing message (no reply_to_message_id).
#     """
#     to = normalize_phone((to or "").strip())
#     if not to:
#         return None

#     body = msg(key, lang, fallback=fallback, **kwargs)

#     out = frappe.get_doc(
#         {
#             "doctype": "WhatsApp Message",
#             "type": "Outgoing",
#             "to": to,
#             "content_type": "text",
#             "message": body,
#             "message_type": "Manual",
#         }
#     )

#     out.insert(ignore_permissions=True)
#     _safe_send(out)
#     return out.name
