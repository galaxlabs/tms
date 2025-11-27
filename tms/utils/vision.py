# tms/utils/vision.py

import frappe


def extract_passenger_from_image(file_doc):
    """
    Convert an image (File doc) into structured passenger data.

    Expected return format:
    {
        "passenger_name": "Muhammad Ali",
        "idpassport_no": "AB1234567",
        "nationality": "PAK",
        "contact_no": "+9665xxxxxxx",
        "ocr_confidence": 92.5
    }

    Implement this using your existing OCR / AI logic.
    """
    file_path = file_doc.get_full_path()

    # TODO: Plug in your real OCR/AI logic using file_path or bytes
    # Example pattern (pseudo):
    #
    # with open(file_path, "rb") as f:
    #     img_bytes = f.read()
    #
    # result = call_your_ocr_api(img_bytes)
    # parsed = parse_result_to_passenger_dict(result)
    #
    # return parsed

    # Temporary dummy result for testing the flow:
    parsed = {
        "passenger_name": "Demo Passenger",
        "idpassport_no": "P123456789",
        "nationality": "PAK",
        "contact_no": None,
        "ocr_confidence": 90,
    }

    return parsed
