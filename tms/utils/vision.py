# tms/utils/vision.py

import json
import frappe
from tms.utils.ocr_utils import extract_text_from_file
from tms.utils.parser import parse_passenger_details


def extract_passenger_from_image(file_doc, waba_msg=None, trip=None):
    """
    Convert an image (File doc) into structured passenger data AND
    create an OCR History record.
    """

    file_url = file_doc.file_url

    # 1) OCR (Tesseract) → raw + fixed
    raw_text, fixed_text = extract_text_from_file(file_url)

    # 2) Parse structured fields
    parsed = parse_passenger_details(raw_text, fixed_text)
    full_name = parsed.get("name")
    id_no = parsed.get("id_no")
    nationality = parsed.get("nationality")

    # 3) Build return payload
    result = {
        "passenger_name": full_name,
        "idpassport_no": id_no,
        "nationality": nationality,
        "contact_no": None,
        "ocr_confidence": 0,  # you can enhance later
    }

    # 4) Create OCR History row
    try:
        ocr_doc = frappe.get_doc({
            "doctype": "OCR History",
            "source": "WABA Image" if waba_msg else "Trip Attachment",
            "ocr_engine": "Tesseract",
            "confidence": 0,
            "reference_doctype": "Trip" if trip else None,
            "reference_name": trip.name if trip else None,
            "waba_message": waba_msg.name if waba_msg else None,
            "trip": trip.name if trip else None,
            "file": file_doc.name,
            # if you later store media_hash in WABA message, add here:
            "media_hash": getattr(waba_msg, "media_hash", None) if waba_msg else None,
            "raw_text": raw_text,
            "fixed_text": fixed_text,
            "full_name": full_name,
            "nationality": nationality,
            "id_no": id_no,
            "json_data": json.dumps(parsed, ensure_ascii=False),
        })
        ocr_doc.insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "[TMS OCR] Failed to save OCR History")

    return result
