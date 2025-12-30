import json

def get_json(doc, fieldname: str, default):
    if not doc or not hasattr(doc, fieldname):
        return default
    raw = getattr(doc, fieldname, None)
    if raw in (None, ""):
        return default
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return default

def set_json(doc, fieldname: str, value):
    if not doc or not hasattr(doc, fieldname):
        return
    try:
        setattr(doc, fieldname, json.dumps(value, ensure_ascii=False))
    except Exception:
        setattr(doc, fieldname, "[]")
