# Copyright (c) 2025, Galaxy Labs and contributors
# For license information, please see license.txt

import frappe
import requests
from frappe.model.document import Document


class Route(Document):
    def validate(self):
        # auto rename only on existing records
        if not self.is_new():
            self.auto_rename_on_change()

    def auto_rename_on_change(self):
        if not (self.from_city and self.to_city):
            return

        desired = f"{self.from_city}-To-{self.to_city}"

        if self.name == desired:
            return

        if getattr(self.flags, "in_auto_rename", False):
            return

        if frappe.db.exists("Route", desired):
            desired = f"{desired}-{frappe.generate_hash(length=4).upper()}"

        self.flags.in_auto_rename = True
        frappe.rename_doc(
            self.doctype,
            self.name,
            desired,
            force=True,
            merge=False
        )
        self.flags.in_auto_rename = False

    @staticmethod
    def clean_place_name(name: str) -> str:
        if not name:
            return ""
        name = name.replace(", Saudi Arabia", "").replace(", United Arab Emirates", "").strip()
        return name.split(",")[0]

    @staticmethod
    def get_place_name(place: str, api_key: str):
        """Get place name in English + Arabic"""
        url = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
        params = {
            "input": place,
            "inputtype": "textquery",
            "fields": "place_id",
            "key": api_key,
        }
        res = requests.get(url, params=params).json()
        if not res.get("candidates"):
            return Route.clean_place_name(place)

        place_id = res["candidates"][0]["place_id"]

        details_url = "https://maps.googleapis.com/maps/api/place/details/json"
        params_en = {"place_id": place_id, "fields": "name", "language": "en", "key": api_key}
        en_data = requests.get(details_url, params=params_en).json()
        en_name = en_data.get("result", {}).get("name", place)

        params_ar = {"place_id": place_id, "fields": "name", "language": "ar", "key": api_key}
        ar_data = requests.get(details_url, params=params_ar).json()
        ar_name = ar_data.get("result", {}).get("name", "")

        return f"{en_name} | {ar_name}" if ar_name else en_name


def _get_api_key():
    api_key = frappe.conf.get("google_maps_api_key")
    if not api_key:
        try:
            settings = frappe.get_single("Google Map Settings")
            api_key = settings.api_key
        except Exception:
            pass
    if not api_key:
        frappe.throw("❌ Google Maps API key not found. Add it in site_config.json or Google Map Settings.")
    return api_key


def _parse_distance_km(distance_text: str) -> float:
    dt = (distance_text or "").lower().replace(",", "").strip()
    if " km" in dt:
        return float(dt.replace(" km", ""))
    if " m" in dt:
        return float(dt.replace(" m", "")) / 1000
    return float("".join(ch for ch in dt if (ch.isdigit() or ch == ".")))


@frappe.whitelist()
def fetch_distance_for_route(route_name: str):
    """
    Fetch distance & duration_minutes for a SAVED Route and update it.
    Uses Route.avg_speed_kmph if set, else fallback to 100.
    """
    if not route_name:
        frappe.throw("Route name is required")

    route = frappe.get_doc("Route", route_name)

    if not route.from_city or not route.to_city:
        frappe.throw("Please set From City and To City first")

    api_key = _get_api_key()

    base_url = "https://maps.googleapis.com/maps/api/distancematrix/json"
    params = {
        "origins": route.from_city,
        "destinations": route.to_city,
        "key": api_key,
        "region": "sa",
    }

    res = requests.get(base_url, params=params)
    data = res.json()

    if data.get("status") != "OK":
        frappe.throw(f"Google API Error: {data.get('status')}")

    el = data["rows"][0]["elements"][0]
    if el.get("status") != "OK":
        frappe.throw(f"Distance Matrix Error: {el.get('status')}")

    distance_text = el["distance"]["text"]
    distance_km = _parse_distance_km(distance_text)

    # ✅ take avg speed from Route field if available
    avg_speed = float(route.avg_speed_kmph or 0) or 100.0
    duration_minutes = max(1, int(round((distance_km / avg_speed) * 60)))

    # ✅ update doc fields (keep from_city/to_city clean)
    route.db_set("distance", distance_km)
    route.db_set("duration_minutes", duration_minutes)
    route.db_set("from_place_full", Route.get_place_name(route.from_city, api_key))
    route.db_set("to_place_full", Route.get_place_name(route.to_city, api_key))

    # optional display text
    try:
        route.db_set("duration", f"{(duration_minutes / 60):.2f} hrs")
    except Exception:
        pass

    return {
        "route": route.name,
        "distance": distance_km,
        "duration_minutes": duration_minutes,
        "avg_speed_used": avg_speed
    }
