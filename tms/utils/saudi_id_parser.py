# # tms/tms/utils/saudi_id_parser.py
from __future__ import annotations
from typing import Optional, Dict, Any, List

import re
from saudi_id_validator import is_valid_saudi_id

SAUDI_ID_REGEX = re.compile(r"\b[12]\d{9}\b")


def extract_id_candidates(text: str) -> List[str]:
    return SAUDI_ID_REGEX.findall(text)


def choose_best_id(candidates: List[str]) -> Optional[str]:
    for candidate in candidates:
        if is_valid_saudi_id(candidate):
            return candidate
    return None


def parse_field_by_anchor(lines: List[str], anchors: List[str]) -> Optional[str]:
    lowered = [ln.lower() for ln in lines]
    anchors_l = [a.lower() for a in anchors]

    for idx, line in enumerate(lowered):
        for anchor in anchors_l:
            if anchor in line:
                original_line = lines[idx]
                parts = re.split(r"[:\-]+", original_line, maxsplit=1)
                if len(parts) == 2 and parts[1].strip():
                    return parts[1].strip()

                if idx + 1 < len(lines):
                    return lines[idx + 1].strip()
    return None


def parse_saudi_id_from_text(raw_text: str) -> Dict[str, Any]:
    lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]

    candidates = extract_id_candidates(raw_text)
    id_no = choose_best_id(candidates)
    id_conf = 0.95 if id_no else 0.2

    full_name = parse_field_by_anchor(
        lines,
        anchors=["الاسم", "اسم حامل البطاقة", "Name"],
    )
    nationality = parse_field_by_anchor(
        lines,
        anchors=["الجنسية", "Nationality"],
    )

    return {
        "engine": "saudi_id_parser",
        "id_no": id_no,
        "id_confidence": id_conf,
        "full_name": full_name,
        "nationality": nationality,
    }





# from __future__ import annotations
# from typing import Optional, Dict, Any, List

# import re
# from saudi_id_validator import is_valid_saudi_id  # from saudi-id-validator


# SAUDI_ID_REGEX = re.compile(r"\b[12]\d{9}\b")  # 10 digits starting with 1 or 2


# def extract_id_candidates(text: str) -> List[str]:
#     """Find all 10-digit Saudi ID/Iqama candidates in text."""
#     return SAUDI_ID_REGEX.findall(text)


# def choose_best_id(candidates: List[str]) -> Optional[str]:
#     """Pick the first valid Saudi ID/Iqama that passes check-digit validation."""
#     for candidate in candidates:
#         if is_valid_saudi_id(candidate):
#             return candidate
#     return None


# def parse_field_by_anchor(lines: List[str], anchors: List[str]) -> Optional[str]:
#     """
#     Given OCR lines and a list of anchor keywords, find the line containing
#     an anchor and return the 'value part' of that line or the next line.
#     """
#     lowered = [ln.lower() for ln in lines]
#     anchors_l = [a.lower() for a in anchors]

#     for idx, line in enumerate(lowered):
#         for anchor in anchors_l:
#             if anchor in line:
#                 # Example patterns: "الاسم: محمد ..." or "Name : MOHAMMAD ..."
#                 original_line = lines[idx]
#                 # Try after colon
#                 parts = re.split(r"[:\-]+", original_line, maxsplit=1)
#                 if len(parts) == 2 and parts[1].strip():
#                     return parts[1].strip()

#                 # Otherwise, maybe value is on the next line
#                 if idx + 1 < len(lines):
#                     return lines[idx + 1].strip()
#     return None


# def parse_saudi_id_from_text(raw_text: str) -> Dict[str, Any]:
#     """
#     Parse a Saudi National ID / Iqama from raw OCR text.
#     Returns a dict with fields that match your OCRHistory structure.
#     """
#     lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]

#     # 1) ID number
#     candidates = extract_id_candidates(raw_text)
#     id_no = choose_best_id(candidates)
#     id_conf = 0.95 if id_no else 0.2

#     # 2) Full name
#     full_name = parse_field_by_anchor(
#         lines,
#         anchors=["الاسم", "اسم حامل البطاقة", "Name"]
#     )

#     # 3) Nationality
#     nationality = parse_field_by_anchor(
#         lines,
#         anchors=["الجنسية", "Nationality"]
#     )

#     return {
#         "engine": "saudi_id_parser",
#         "id_no": id_no,
#         "id_confidence": id_conf,
#         "full_name": full_name,
#         "nationality": nationality,
#         # You can add more (dob, expiry) later using anchors "تاريخ الميلاد", "تاريخ الانتهاء"
#     }
