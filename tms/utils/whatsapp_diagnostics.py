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
@frappe.whitelist()
def test_send_trip_slip_ready(to: str, public_pdf_url: str, customer_name: str = "Customer"):
    s, token = _get_settings()
    version = s.version
    phone_id = s.phone_id

    if not phone_id:
        frappe.throw("Phone ID is missing in WhatsApp Settings")

    if not to:
        frappe.throw("Recipient number is required")

    to = to.strip().replace(" ", "")
    if to.startswith("+"):
        to = to[1:]

    if not public_pdf_url.startswith("http"):
        frappe.throw("public_pdf_url must be a full https URL")

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": "trip_slip_ready",
            "language": {"code": "en"},
            "components": [
                {
                    "type": "header",
                    "parameters": [{
                        "type": "document",
                        "document": {
                            "link": public_pdf_url,
                            "filename": "Trip Slip.pdf"
                        }
                    }]
                },
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": customer_name}
                    ]
                }
            ]
        }
    }

    url = f"{GRAPH_BASE}/{version}/{phone_id}/messages"
    r = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload,
        timeout=20
    )
    try:
        body = r.json()
    except Exception:
        body = r.text

    return {
        "url": url,
        "http_status": r.status_code,
        "request_payload": payload,
        "response": body
    }
