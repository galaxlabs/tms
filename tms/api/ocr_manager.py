# tms/tms/api/ocr_manager.py

import base64
import json
import re
from typing import List, Dict, Any

import frappe
import requests
from openai import OpenAI
from frappe.utils import get_url, now_datetime


# ---------------------------------------------------------------------------
# OpenAI integration
# ---------------------------------------------------------------------------

def _get_openai_client() -> OpenAI:
    api_key = frappe.conf.get("openai_api_key")
    if not api_key:
        frappe.throw("OpenAI API key (openai_api_key) is not set in site_config.json")
    return OpenAI(api_key=api_key)


def extract_id_info_from_bytes(file_bytes: bytes) -> Dict[str, str]:
    """
    Send image/PDF bytes to ChatGPT and extract:
      - name
      - nationality
      - id_no

    Returns:
      { "full_name": ..., "nationality": ..., "id_no": ... }
    """
    client = _get_openai_client()

    b64_data = base64.b64encode(file_bytes).decode("utf-8")

    prompt = """
    You are an extraction bot for a transport booking system.
    The user sends an ID/passport or similar document.

    Extract ONLY:
      - full name of the person (call it "full_name")
      - nationality (country name, in English, call it "nationality")
      - ID number (national ID, Iqama or passport; call it "id_no")

    Respond ONLY with a JSON object like:
    {
      "full_name": "...",
      "nationality": "...",
      "id_no": "..."
    }

    If any value is missing, use empty string for that key.
    """

    response = client.chat.completions.create(
        model="gpt-4.1-mini",  # adjust to the model you want
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:application/octet-stream;base64,{b64_data}"
                        },
                    },
                ],
            }
        ],
        temperature=0,
    )

    content = response.choices[0].message.content

    # Try to parse JSON safely
    try:
        data = json.loads(content)
    except Exception:
        match = re.search(r"\{.*\}", content, flags=re.S)
        data = json.loads(match.group(0)) if match else {}

    full_name = (data.get("full_name") or "").strip()
    nationality = (data.get("nationality") or "").strip()
    id_no = (data.get("id_no") or "").strip()

    return {
        "full_name": full_name,
        "nationality": nationality,
        "id_no": id_no,
    }


# ---------------------------------------------------------------------------
# Driver and Trip lookup
# ---------------------------------------------------------------------------

def _normalize_phone(phone: str) -> str:
    """Remove spaces, dashes, etc. Keep digits and +."""
    if not phone:
        return ""
    return re.sub(r"[^\d+]", "", phone)


def find_driver_by_phone(sender_phone: str):
    """
    Try to find Staff where mobile_no matches sender_phone and is_driver == 1.
    Matching is loose (by last 8 digits).
    """
    clean = _normalize_phone(sender_phone)
    if not clean:
        return None

    candidates = frappe.get_all(
        "Staff",
        filters={"is_driver": 1},
        fields=["name", "full_name", "mobile_no"],
        limit=100,
    )

    for c in candidates:
        mobile = _normalize_phone(c.get("mobile_no") or "")
        if not mobile:
            continue

        # match by last 8 digits
        if mobile.endswith(clean[-8:]):
            return c

    return None


def find_active_trip_for_driver(staff_name: str):
    """
    Get the latest scheduled/departed trip for the driver.
    Adjust filters as needed for your logic.
    """
    trips = frappe.get_all(
        "Trip",
        filters={
            "driver": staff_name,
            "trip_status": ["in", ["Scheduled", "Departed"]],
        },
        fields=["name"],
        order_by="departure asc",
        limit=1,
    )
    if not trips:
        return None

    return frappe.get_doc("Trip", trips[0]["name"])


# ---------------------------------------------------------------------------
# Reply builder
# ---------------------------------------------------------------------------

def build_trip_links(trip) -> Dict[str, str]:
    """Generate public website URL and PDF URL for Trip."""
    base = get_url()

    # Website route from Trip.route (UUID based)
    if trip.route:
        web_url = f"{base.rstrip('/')}/{trip.route.lstrip('/')}"
    else:
        web_url = f"{base.rstrip('/')}/trip?name={trip.name}"

    pdf_url = (
        f"{base.rstrip('/')}"
        "/api/method/frappe.utils.print_format.download_pdf"
        f"?doctype=Trip&name={trip.name}&format=Trip&no_letterhead=0"
    )

    return {"web_url": web_url, "pdf_url": pdf_url}


def build_whatsapp_reply(trip, passengers: List[Dict[str, str]]) -> str:
    """Create human readable WhatsApp message."""
    links = build_trip_links(trip)
    lines = []

    lines.append("✅ Passenger(s) added to your trip.")
    lines.append("")
    lines.append(f"Trip: {trip.name}")
    if trip.from_location and trip.to_location:
        lines.append(f"Route: {trip.from_location} → {trip.to_location}")
    if trip.departure:
        lines.append(f"Departure: {trip.departure}")
    if trip.arrival:
        lines.append(f"Arrival (estimated): {trip.arrival}")
    lines.append("")

    for p in passengers:
        lines.append(f"Passenger: {p.get('full_name')}")
        if p.get("nationality"):
            lines.append(f"Nationality: {p.get('nationality')}")
        if p.get("id_no"):
            lines.append(f"ID: {p.get('id_no')}")
        lines.append("")

    lines.append("🔗 Trip details:")
    lines.append(links["web_url"])
    lines.append("")
    lines.append("📄 Trip PDF:")
    lines.append(links["pdf_url"])

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# MAIN WHATSAPP ENTRY – keep it simple, no file attachments in ERP
# ---------------------------------------------------------------------------

@frappe.whitelist(allow_guest=True)
def process_whatsapp_message(
    sender_phone: str | None = None,
    media_urls: str | None = None,
    api_secret: str | None = None,
):
    """
    WhatsApp webhook entry.
    - sender_phone: WhatsApp sender number (+9665xxxx)
    - media_urls: JSON array or comma separated list of image/PDF URLs
    - api_secret: shared secret for security (optional but recommended)
    """

    # quick validation to avoid TypeError
    if not sender_phone:
        return {"success": False, "error": "sender_phone is required"}

    # 1) Security check
    expected = frappe.conf.get("whatsapp_api_secret")
    if expected and api_secret != expected:
        frappe.local.response["http_status_code"] = 403
        return {"success": False, "error": "Invalid API secret"}

    # 2) Parse media list
    if not media_urls:
        return {"success": False, "error": "No media URLs provided"}

    if isinstance(media_urls, str):
        try:
            media_list = json.loads(media_urls)
            if not isinstance(media_list, list):
                media_list = [media_list]
        except Exception:
            media_list = [u.strip() for u in media_urls.split(",") if u.strip()]
    else:
        media_list = media_urls

    if not media_list:
        return {"success": False, "error": "No valid media URLs"}

    # 3) Find driver (Staff)
    driver = find_driver_by_phone(sender_phone)
    if not driver:
        return {
            "success": False,
            "error": "No driver (Staff) found for this phone number",
            "sender_phone": sender_phone,
        }

    # 4) Find active trip
    trip = find_active_trip_for_driver(driver["name"])
    if not trip:
        return {
            "success": False,
            "error": "No active Trip found for this driver",
            "driver": driver,
        }

    added_passengers: list[dict[str, str]] = []

    # 5) Process each media URL
    for url in media_list:
        try:
            headers = {}  # add auth if your WA provider needs it
            resp = requests.get(url, headers=headers, timeout=20)
            resp.raise_for_status()
            file_bytes = resp.content

            info = extract_id_info_from_bytes(file_bytes)

            if info.get("full_name"):
                trip.append(
                    "passengers",
                    {
                        "full_name": info["full_name"],
                        "id_no": info["id_no"],
                        "nationality": info["nationality"],
                    },
                )
                added_passengers.append(info)

        except Exception as e:
            frappe.log_error(f"Error processing media {url}: {e}", "WhatsApp OCR")

    if added_passengers:
        trip.save(ignore_permissions=True)
        frappe.db.commit()

    reply_text = build_whatsapp_reply(trip, added_passengers)

    return {
        "success": True,
        "driver": driver,
        "trip": trip.name,
        "passengers_added_count": len(added_passengers),
        "reply_text": reply_text,
    }
