import json
import frappe

_CACHE = {"doc": None, "templates": None}

def get_settings():
    """Returns (settings_doc, templates_dict). Cached per worker."""
    if _CACHE["doc"] and _CACHE["templates"] is not None:
        return _CACHE["doc"], _CACHE["templates"]

    doc = frappe.get_single("WhatsApp Bot Settings")
    try:
        templates = json.loads(doc.message_templates or "{}")
        if not isinstance(templates, dict):
            templates = {}
    except Exception:
        templates = {}

    _CACHE["doc"] = doc
    _CACHE["templates"] = templates
    return doc, templates

def clear_settings_cache():
    _CACHE["doc"] = None
    _CACHE["templates"] = None

def normalize_lang(lang: str) -> str:
    lang = (lang or "").strip().lower()
    # accept common user inputs
    if lang in ("eng", "english"):
        return "en"
    if lang in ("arabic", "ar"):
        return "ar"
    if lang in ("urdu", "ur"):
        return "ur"
    if lang in ("en", "ar", "ur"):
        return lang
    return "en"

def get_message(key: str, lang: str = None, **kwargs) -> str:
    doc, templates = get_settings()
    lang = normalize_lang(lang or doc.default_language)

    entry = templates.get(key) or {}
    if not isinstance(entry, dict):
        entry = {}

    text = entry.get(lang) or entry.get("en") or ""
    try:
        return text.format(**kwargs)
    except Exception:
        # if formatting failed, return raw text
        return text
