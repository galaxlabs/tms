# passenger_parser.py
import re

def parse_passenger_details(ocr_text):
    """
    A simple parser function. You will need to customize the logic
    based on the text structure returned by your OCR service.
    """
    # Example parsing logic (replace with your actual logic)
    name = None
    id_no = None
    nationality = None

    # Very basic example: look for patterns
    name_match = re.search(r'(?:Name|اسم)[:\s]*([A-Za-z\u0600-\u06FF\s]+)', ocr_text)
    if name_match:
        name = name_match.group(1).strip()

    id_match = re.search(r'(?:ID|رقم|Passport)[:\s]*([A-Z0-9]+)', ocr_text)
    if id_match:
        id_no = id_match.group(1).strip()

    nationality_match = re.search(r'(?:Nationality|جنسية)[:\s]*([A-Za-z\u0600-\u06FF\s]+)', ocr_text)
    if nationality_match:
        nationality = nationality_match.group(1).strip()

    return {
        "name": name,
        "id_no": id_no,
        "nationality": nationality
    }