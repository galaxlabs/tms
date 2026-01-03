# tms/utils/whatsapp_bot/helpers/json_store.py
import json
import frappe


def get_json(doc, fieldname: str, default=None):
    if default is None:
        default = []

    raw = getattr(doc, fieldname, None)
    if raw is None:
        raw = frappe.db.get_value(doc.doctype, doc.name, fieldname)

    if not raw:
        return default

    try:
        return json.loads(raw)
    except Exception:
        return default


def set_json(doc, fieldname: str, value):
    raw = json.dumps(value, ensure_ascii=False)
    frappe.db.set_value(doc.doctype, doc.name, fieldname, raw, update_modified=False)
    setattr(doc, fieldname, raw)
    return value

# import json

# def get_json(doc, fieldname: str, default):
#     if not doc or not hasattr(doc, fieldname):
#         return default
#     raw = getattr(doc, fieldname, None)
#     if raw in (None, ""):
#         return default
#     if isinstance(raw, (dict, list)):
#         return raw
#     try:
#         return json.loads(raw)
#     except Exception:
#         return default

# def set_json(doc, fieldname: str, value):
#     if not doc or not hasattr(doc, fieldname):
#         return
#     try:
#         setattr(doc, fieldname, json.dumps(value, ensure_ascii=False))
#     except Exception:
#         setattr(doc, fieldname, "[]")
