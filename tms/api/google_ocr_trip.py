import frappe, io, json
from google.cloud import vision


def _init_vision_client():
    key_path = frappe.conf.get("google_vision_key_path")
    if not key_path:
        frappe.throw("⚠️ Google Vision key path missing in site_config.json")
    return vision.ImageAnnotatorClient.from_service_account_json(key_path)


@frappe.whitelist()
def extract_passengers_from_trip(trip_name):
    """Extract passenger details from trip attachments using Google Vision OCR."""
    client = _init_vision_client()
    trip = frappe.get_doc("Trip", trip_name)

    # Get all attached images
    files = frappe.get_all(
        "File",
        filters={"attached_to_doctype": "Trip", "attached_to_name": trip_name},
        fields=["file_url"]
    )

    if not files:
        frappe.throw("❌ No attachments found for this Trip.")

    passengers = []
    for f in files:
        try:
            file_path = frappe.get_site_path(f.file_url.lstrip("/"))
            with io.open(file_path, "rb") as image_file:
                content = image_file.read()

            image = vision.Image(content=content)
            response = client.text_detection(image=image)

            if not response.text_annotations:
                continue

            text = response.text_annotations[0].description
            passenger = parse_passenger_text(text)

            if passenger:
                trip.append("passengers", passenger)
                passengers.append({
                    **passenger,
                    "source_file": f.file_url,
                    "extracted_text": text[:300]  # Store preview for debugging
                })

        except Exception as e:
            frappe.log_error(f"Google OCR failed for {f.file_url}: {e}")

    trip.save(ignore_permissions=True)
    frappe.db.commit()

    return {
        "trip": trip.name,
        "ocr_source": "google_vision",
        "passengers_extracted": len(passengers),
        "passengers": passengers
    }


def parse_passenger_text(text: str):
    """Lightweight regex parser to extract name, ID, nationality."""
    import re
    text = text.replace("\n", " ").strip()

    name = re.search(r"(?:Name|الاسم)[:\-]?\s*([A-Za-z\u0600-\u06FF ]{3,})", text)
    id_no = re.search(r"(?:ID|رقم الهوية|Passport)[:\-]?\s*([A-Z0-9]{5,})", text)
    nationality = re.search(r"(?:Nationality|الجنسية)[:\-]?\s*([A-Za-z\u0600-\u06FF ]+)", text)

    if not name:
        return None

    return {
        "passenger_name": name.group(1).strip(),
        "idpassport_no": id_no.group(1).strip() if id_no else "",
        "nationality": nationality.group(1).strip() if nationality else ""
    }
