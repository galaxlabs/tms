# Copyright (c) 2025, Galaxy Labs and contributors
# For license information, please see license.txt

import frappe
import requests
from frappe.model.document import Document


class Route(Document):

	def clean_place_name(name: str) -> str:
		"""Simplify place names by removing country etc."""
		if not name:
			return ""
		name = name.replace(", Saudi Arabia", "").replace(", United Arab Emirates", "").strip()
		return name.split(",")[0]

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

		# Step 2: English details
		details_url = "https://maps.googleapis.com/maps/api/place/details/json"
		params_en = {
			"place_id": place_id,
			"fields": "name",
			"language": "en",
			"key": api_key,
		}
		en_data = requests.get(details_url, params=params_en).json()
		en_name = en_data.get("result", {}).get("name", place)

		# Step 3: Arabic details
		params_ar = {
			"place_id": place_id,
			"fields": "name",
			"language": "ar",
			"key": api_key,
		}
		ar_data = requests.get(details_url, params=params_ar).json()
		ar_name = ar_data.get("result", {}).get("name", "")

		return f"{en_name} | {ar_name}" if ar_name else en_name


@frappe.whitelist()
def get_distance(from_city, to_city):
	"""Fetch distance & duration from Google Maps Distance Matrix API"""

	api_key = frappe.conf.get("google_maps_api_key")

	# ✅ fallback to your custom single doctype if not found in config
	if not api_key:
		try:
			settings = frappe.get_single("Google Map Settings")
			api_key = settings.api_key
		except Exception:
			pass

	if not api_key:
		frappe.throw("❌ Google Maps API key not found. Add it in site_config.json or Google Map Settings.")

	base_url = "https://maps.googleapis.com/maps/api/distancematrix/json"
	params = {
		"origins": from_city,
		"destinations": to_city,
		"key": api_key,
		"region": "sa",
	}

	try:
		res = requests.get(base_url, params=params)
		data = res.json()

		if data.get("status") != "OK":
			frappe.throw(f"Google API Error: {data.get('status')}")

		row = data["rows"][0]["elements"][0]
		distance_text = row["distance"]["text"]
		duration_text = row["duration"]["text"]

		distance_km = float(distance_text.replace(" km", "").replace(",", ""))
		custom_duration_hours = round(distance_km / 115, 2)

		return {
			"from_city": Route.get_place_name(from_city, api_key),
			"to_city": Route.get_place_name(to_city, api_key),
			"distance": distance_km,
			"duration": f"{custom_duration_hours} hrs",
			"google_duration": duration_text,
		}

	except Exception as e:
		frappe.throw(f"Error fetching data: {str(e)}")
