import os
import frappe
from frappe.utils import nowdate
from pathlib import Path

# OCR engines
from tms.utils.openai_ocr_utils import extract_text_openai
from tms.utils.ocr_utils import extract_text_from_file
from tms.utils.parser import parse_passenger_details

@frappe.whitelist(allow_guest=False)
def create_trip_from_ocr(file_url: str):
    """
    Create a Trip document automatically from an uploaded ID image.
    Priority: GPT-4o (OpenAI) OCR → fallback to Tesseract-based OCR.
    """

    try:
        # 1️⃣ Resolve file path
        file_path = frappe.get_site_path("private", "files", Path(file_url).name)
        if not os.path.exists(file_path):
            frappe.throw(f"File not found: {file_path}")

        # 2️⃣ Try OpenAI GPT-4o OCR
        try:
            frappe.logger().info("[OCR] Trying OpenAI GPT-4o Vision OCR...")
            text = extract_text_openai(file_path)
            if not text or len(text.strip()) < 10:
                raise ValueError("Empty OCR response from OpenAI")
        except Exception as e:
            frappe.logger().warning(f"[OCR] OpenAI OCR failed → fallback: {e}")

            # 3️⃣ Fallback to Tesseract OCR (offline)
            raw, fixed = extract_text_from_file(file_url)
            text = fixed or raw

        frappe.logger().info(f"[OCR Output]: {text[:400]}")

        # 4️⃣ Parse structured info (Name / ID / Nationality)
        passenger = parse_passenger_details(text, text)
        frappe.logger().info(f"[Parsed Passenger]: {passenger}")

        if not passenger.get("name"):
            frappe.throw("Passenger name not detected — please recheck the uploaded image.")

        # 5️⃣ Match nationality to Country DocType
        country = None
        if passenger.get("nationality"):
            country = frappe.db.get_value(
                "Country",
                {"country_name": ["like", f"%{passenger.get('nationality')}%"]},
                "name",
            )

        # 6️⃣ Create new Trip document
        trip = frappe.new_doc("Trip")
        trip.driver_name = "Imran Khan"
        trip.route = "Madina - Makkah"
        trip.departure_time = frappe.utils.now_datetime()
        trip.travel_date = nowdate()

        # 7️⃣ Append passengers
        trip.append("passengers", {
            "passenger_name": passenger.get("name"),
            "idpassport_no": passenger.get("id_no"),
            "nationality": country or passenger.get("nationality"),
            "contact_no": "",
        })

        # 8️⃣ Save & insert document
        trip.insert(ignore_permissions=True)
        trip.save(ignore_permissions=True)

        frappe.logger().info(f"[Trip Created]: {trip.name}")

        # 9️⃣ Clean up uploaded file record
        frappe.delete_doc_if_exists("File", {"file_url": file_url})

        # ✅ Return success
        return {
            "trip_name": trip.name,
            "passengers": trip.passengers,
            "ocr_source": "openai_gpt4o"
        }

    except Exception as e:
        frappe.log_error(f"OCR Trip creation failed: {e}", "OCR Trip Error")
        raise
@frappe.whitelist(allow_guest=False)
def test_ocr_extraction(file_url: str):
    """
    Just run OCR + parsing (no Trip creation).
    Returns structured extraction results.
    """

    from pathlib import Path
    from tms.utils.openai_ocr_utils import extract_text_openai
    from tms.utils.ocr_utils import extract_text_from_file
    from tms.utils.parser import parse_passenger_details

    file_path = frappe.get_site_path("private", "files", Path(file_url).name)

    try:
        # Try OpenAI OCR first
        frappe.logger().info("[OCR Test] Trying OpenAI GPT-4o...")
        text = extract_text_openai(file_path)
    except Exception as e:
        frappe.logger().warning(f"[OCR Test] OpenAI failed: {e} — fallback to Tesseract.")
        raw, fixed = extract_text_from_file(file_url)
        text = fixed or raw

    # Parse the extracted text
    passenger = parse_passenger_details(text, text)

    # Return just the parsed fields for testing
    return {
        "ocr_source": "openai_gpt4o",
        "raw_text": text[:500],
        "parsed": passenger
    }



# import frappe
# from frappe.utils import nowdate, now
# from tms.utils.hf_ocr_utils import extract_text_from_image as extract_text_from_file
# from tms.utils.parser import parse_passenger_details

# @frappe.whitelist(allow_guest=False)
# def create_trip_from_ocr(file_url):
#     # Extract text
#     text = extract_text_from_file(file_url)
#     passenger = parse_passenger_details(text)

#     # Resolve nationality
#     country = frappe.db.get_value("Country", {"country_name": passenger.get("nationality")}, "name")

#     # Create Trip
#     trip = frappe.new_doc("Trip")
#     trip.title = f"{passenger.get('name')} - OCR Trip"
#     trip.route = "Madina-Makkah"
#     trip.departure_time = now()
#     trip.driver_name = "Imran Khan"
#     trip.travel_date = nowdate()

#     # Explicitly create child row
#     passenger_row = frappe.new_doc("Passengers")
#     passenger_row.passenger_name = passenger.get("name")
#     passenger_row.idpassport_no = passenger.get("id_no")
#     passenger_row.nationality = country

#     # Manually link parent fields
#     passenger_row.parent = trip.name  # parent will be set after insert
#     passenger_row.parentfield = "passengers"
#     passenger_row.parenttype = "Trip"

#     # Append safely
#     trip.set("passengers", [passenger_row])

#     # Insert
#     trip.insert(ignore_permissions=True)

#     # Clean up OCR file
#     frappe.delete_doc_if_exists("File", {"file_url": file_url})

#     return {"trip_name": trip.name, "passengers": [p.as_dict() for p in trip.passengers]}
# //////////////////////////////////////////////////////////////////
# import frappe
# from frappe.utils import nowdate, now
# from tms.utils.ocr_utils import extract_text_from_file
# from tms.utils.parser import parse_passenger_details


# @frappe.whitelist(allow_guest=False)
# def create_trip_from_ocr(file_url):
#     """
#     OCR function that:
#     - Extracts passenger details from uploaded image
#     - Creates Trip document
#     - Fills Passengers child table
#     - Lets trip.py handle post-create logic (QR, public view, etc.)
#     """

#     # 1️⃣ Extract text from image
#     text = extract_text_from_file(file_url)
#     passenger = parse_passenger_details(text)

#     # 2️⃣ Resolve nationality (optional)
#     country = frappe.db.get_value("Country", {"country_name": passenger.get("nationality")}, "name")

#     # 3️⃣ Create new Trip record
#     trip = frappe.new_doc("Trip")
#     trip.title = f"{passenger.get('name')} - OCR Trip"
#     trip.route = "Madina-Makkah"
#     trip.departure_time = now()
#     trip.driver_name = "Imran Khan"


#     # 4️⃣ Add passenger child record
#     trip.append("passengers", {
#         "passenger_name": passenger.get("name"),
#         "idpassport_no": passenger.get("id_no"),
#         "nationality": country
#     })

#     # 5️⃣ Insert document (let after_insert handle visibility + QR)
#     trip.insert(ignore_permissions=True)

#     # 6️⃣ Remove the uploaded file after OCR
#     frappe.delete_doc_if_exists("File", {"file_url": file_url})

#     return {"trip_name": trip.name}
