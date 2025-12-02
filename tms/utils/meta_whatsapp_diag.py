
# import json
# import frappe
# import requests

# GRAPH_BASE = "https://graph.facebook.com"

# def _call(url, headers, params=None, method="GET"):
#     r = requests.request(method, url, headers=headers, params=params, timeout=30)
#     try:
#         data = r.json()
#     except Exception:
#         data = {"raw": r.text}
#     return r.status_code, data

# @frappe.whitelist()
# def run(action="all"):
#     diag = frappe.get_single("Meta WhatsApp Diagnostics")
#     if not diag.enabled:
#         frappe.throw("Enable Meta WhatsApp Diagnostics first.")

#     token = diag.get_password("token")
#     if not token:
#         frappe.throw("Token is required.")

#     v = (diag.api_version or "v24.0").strip()
#     headers = {"Authorization": f"Bearer {token}"}

#     out = {"version": v, "action": action, "results": {}}
#     http_status = 0
#     last_error = ""

#     try:
#         # 1) List WABAs under Business (Portfolio)
#         if action in ("all", "list_wabas"):
#             if not diag.business_id:
#                 out["results"]["list_wabas"] = {"error": "business_id missing"}
#             else:
#                 url = f"{GRAPH_BASE}/{v}/{diag.business_id}/owned_whatsapp_business_accounts"
#                 http_status, data = _call(url, headers, params={"fields": "id,name"})
#                 out["results"]["list_wabas"] = {"http_status": http_status, "data": data}

#         # 2) WABA basic info
#         if action in ("all", "waba_info"):
#             if not diag.waba_id:
#                 out["results"]["waba_info"] = {"error": "waba_id missing"}
#             else:
#                 url = f"{GRAPH_BASE}/{v}/{diag.waba_id}"
#                 http_status, data = _call(url, headers, params={"fields": "id,name"})
#                 out["results"]["waba_info"] = {"http_status": http_status, "data": data}

#         # 3) Phone numbers in WABA
#         if action in ("all", "phone_numbers"):
#             if not diag.waba_id:
#                 out["results"]["phone_numbers"] = {"error": "waba_id missing"}
#             else:
#                 url = f"{GRAPH_BASE}/{v}/{diag.waba_id}/phone_numbers"
#                 http_status, data = _call(url, headers, params={"fields": "id,display_phone_number,verified_name,quality_rating"})
#                 out["results"]["phone_numbers"] = {"http_status": http_status, "data": data}

#         # 4) Subscribed apps (webhook subscription) list
#         if action in ("all", "subscribed_apps"):
#             if not diag.waba_id:
#                 out["results"]["subscribed_apps"] = {"error": "waba_id missing"}
#             else:
#                 url = f"{GRAPH_BASE}/{v}/{diag.waba_id}/subscribed_apps"
#                 http_status, data = _call(url, headers, params={"fields": "id,name"})
#                 out["results"]["subscribed_apps"] = {"http_status": http_status, "data": data}

#         # 5) Subscribe this app to the WABA (required for receiving real webhooks)
#         if action in ("subscribe",):
#             if not diag.waba_id:
#                 out["results"]["subscribe"] = {"error": "waba_id missing"}
#             else:
#                 url = f"{GRAPH_BASE}/{v}/{diag.waba_id}/subscribed_apps"
#                 http_status, data = _call(url, headers, method="POST")
#                 out["results"]["subscribe"] = {"http_status": http_status, "data": data}

#     except Exception as e:
#         last_error = frappe.get_traceback()
#         out["error"] = str(e)

#     # Save results on the Single doctype
#     diag.last_http_status = int(http_status or 0)
#     diag.last_response = json.dumps(out, indent=2, ensure_ascii=False)
#     diag.last_error = last_error or ""
#     diag.last_run_on = frappe.utils.now()
#     diag.save(ignore_permissions=True)

#     return out
