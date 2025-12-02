import frappe
import requests

GRAPH_BASE = "https://graph.facebook.com"

def _get_settings():
    s = frappe.get_single("WhatsApp Settings")
    if not s.enabled:
        frappe.throw("WhatsApp Settings is disabled")
    token = s.get_password("token")
    if not token:
        frappe.throw("Token is missing in WhatsApp Settings")
    if not s.version:
        frappe.throw("Version is missing (e.g. v24.0)")
    if not s.business_id:
        frappe.throw("Put your WABA ID in WhatsApp Settings > Business ID (792765033788045)")
    return s, token

def _graph_get(version, token, path, params=None):
    url = f"{GRAPH_BASE}/{version}/{path.lstrip('/')}"
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"}, params=params, timeout=20)
    try:
        body = r.json()
    except Exception:
        body = r.text
    return {"url": r.url, "http_status": r.status_code, "data": body}

@frappe.whitelist()
def run_whatsapp_diagnostics():
    s, token = _get_settings()
    version = s.version
    waba_id = s.business_id   # using your existing field as WABA ID
    phone_id = s.phone_id

    out = {
        "waba_info": _graph_get(version, token, f"{waba_id}", {"fields": "id,name"}),
        "phone_numbers": _graph_get(version, token, f"{waba_id}/phone_numbers", {"fields": "id,display_phone_number,verified_name,quality_rating"}),
        "subscribed_apps": _graph_get(version, token, f"{waba_id}/subscribed_apps", {"fields": "id,name"}),
    }
    if phone_id:
        out["phone_id_info"] = _graph_get(version, token, f"{phone_id}", {"fields": "id,display_phone_number,verified_name,quality_rating"})

    return out
