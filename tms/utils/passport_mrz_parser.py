# tms/tms/utils/passport_mrz_parser.py

from __future__ import annotations
from typing import Optional, Dict, Any, List
import re

# Optional: image-based MRZ via PassportEye
try:
    from passporteye import read_mrz
except ImportError:
    read_mrz = None


# ----------------------------------------------------------------------
# 1) IMAGE-BASED MRZ (PassportEye) - OPTIONAL
# ----------------------------------------------------------------------


def parse_passport_mrz(local_path: str) -> Optional[Dict[str, Any]]:
    """
    Parse MRZ from a passport image using PassportEye.
    Returns a dict or None if MRZ not found or library missing.
    """
    if read_mrz is None:
        return None

    mrz = read_mrz(local_path)
    if mrz is None:
        return None

    data = mrz.to_dict()

    raw_surname = (data.get("surname") or "").replace("<", " ").strip()
    raw_names = (data.get("names") or "").replace("<", " ").strip()
    full_name = " ".join([raw_names, raw_surname]).strip()

    valid_score = data.get("valid_score", 0)
    confidence = max(0.5, min(1.0, valid_score / 100.0))

    return {
        "engine": "passporteye",
        "confidence": confidence,
        "raw_mrz": data.get("raw", ""),
        "valid_score": valid_score,
        "document_type": data.get("type"),
        "country": data.get("country"),
        "surname": raw_surname,
        "given_names": raw_names,
        "full_name": full_name,
        "id_no": data.get("number"),
        "nationality": data.get("nationality"),
        "dob": data.get("date_of_birth"),
        "expiry": data.get("expiration_date"),
        "sex": data.get("sex"),
        "personal_number": data.get("personal_number"),
    }


# ----------------------------------------------------------------------
# 2) TEXT-BASED MRZ (from OCR text) - GENERIC + FALLBACK
# ----------------------------------------------------------------------

MRZ_LINE_PATTERN = re.compile(r"^[A-Z0-9< ]{30,60}$")


def _clean_mrz_line(line: str) -> str:
    return line.replace(" ", "").strip()


def _find_mrz_lines(raw_text: str) -> Optional[List[str]]:
    """
    Try to find two MRZ-like lines in OCR text.
    We take the last 2 lines that match the MRZ pattern.
    """
    candidates: List[str] = []

    for ln in raw_text.splitlines():
        t = ln.strip()
        if MRZ_LINE_PATTERN.match(t):
            candidates.append(t)

    if len(candidates) >= 2:
        return [_clean_mrz_line(candidates[-2]), _clean_mrz_line(candidates[-1])]

    return None


def _parse_td3_from_lines(mrz_lines: List[str]) -> Optional[Dict[str, Any]]:
    """
    Parse standard TD3 MRZ (2 lines of 44 chars) if we actually have them.
    """
    if len(mrz_lines) < 2:
        return None

    line1, line2 = mrz_lines

    if len(line1) < 44:
        line1 = line1.ljust(44, "<")
    if len(line2) < 44:
        line2 = line2.ljust(44, "<")

    try:
        doc_type = line1[0]
        country = line1[2:5]
        names_raw = line1[5:]

        name_parts = names_raw.split("<<")
        surname_raw = name_parts[0]
        given_raw = " ".join(p for p in name_parts[1:] if p)

        surname = surname_raw.replace("<", " ").strip()
        given_names = given_raw.replace("<", " ").strip()
        full_name = " ".join([given_names, surname]).strip()

        passport_no = line2[0:9].replace("<", "").strip()
        nationality = line2[10:13]
        dob = line2[13:19]
        sex = line2[20]
        expiry = line2[21:27]
        personal_number = line2[28:42].replace("<", "").strip()

    except Exception:
        return None

    return {
        "engine": "text_mrz",
        "confidence": 0.9,
        "raw_mrz": "\n".join(mrz_lines),
        "valid_score": 90,
        "document_type": doc_type,
        "country": country,
        "surname": surname,
        "given_names": given_names,
        "full_name": full_name,
        "id_no": passport_no,
        "nationality": nationality,
        "dob": dob,
        "expiry": expiry,
        "sex": sex,
        "personal_number": personal_number,
    }


# Fallback: pattern for "compressed" second line like:
# "CM05714924 PAK8902188F 28102493110160491492<72"
LINE2_FALLBACK_RE = re.compile(
    r"^(?P<pass>[A-Z0-9]{7,10})\s+"
    r"(?P<nat>[A-Z]{3})"
    r"(?P<dob>\d{6})\d[A-Z]\s+"
    r"(?P<exp>\d{6})"
)


def _parse_fallback_line2(raw_text: str) -> Optional[Dict[str, Any]]:
    """
    Handle OCR outputs like:
    'CM05714924 PAK8902188F 28102493110160491492<72'
    where MRZ is basically in a single line.
    """
    for ln in raw_text.splitlines():
        s = ln.strip().upper()
        m = LINE2_FALLBACK_RE.match(s)
        if not m:
            continue

        passport_no = m.group("pass")
        nationality = m.group("nat")
        dob = m.group("dob")      # YYMMDD
        expiry = m.group("exp")   # YYMMDD

        return {
            "engine": "text_mrz_fallback",
            "confidence": 0.8,
            "raw_mrz": s,
            "valid_score": 80,
            "document_type": "P",  # assume passport
            "country": nationality,
            "surname": "",
            "given_names": "",
            "full_name": "",
            "id_no": passport_no,
            "nationality": nationality,
            "dob": dob,
            "expiry": expiry,
            "sex": "",
            "personal_number": "",
        }

    return None


def parse_passport_mrz_from_text(raw_text: str) -> Optional[Dict[str, Any]]:
    """
    High-level MRZ-from-text parser:

    1) Try to detect real 2-line MRZ and parse TD3.
    2) If that fails, try fallback single-line pattern (like your GVision output).
    """
    # 1) Try proper 2-line MRZ
    mrz_lines = _find_mrz_lines(raw_text)
    if mrz_lines:
        td3 = _parse_td3_from_lines(mrz_lines)
        if td3:
            return td3

    # 2) Fallback to single-line pattern
    fallback = _parse_fallback_line2(raw_text)
    if fallback:
        return fallback

    return None
