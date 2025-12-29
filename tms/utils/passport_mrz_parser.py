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

MRZ_LINE_PATTERN = re.compile(r"^[A-Z0-9<«‹> ]{30,60}$")


def _normalize_mrz_chars(s: str) -> str:
    """Normalize common OCR confusions seen in MRZ blocks."""
    if not s:
        return ""

    s = s.upper()
    # Some OCR engines output guillemets/angled quotes instead of '<'
    s = s.replace("«", "<").replace("‹", "<").replace(">", "<")
    # Rare: pipes instead of I, commas instead of '<'
    s = s.replace("|", "I").replace(",", "<")
    return s


def _fix_mrz_numeric(s: str) -> str:
    """Fix OCR confusions in numeric MRZ fields (passport no, dates, etc.)."""
    if not s:
        return ""
    s = _normalize_mrz_chars(s)
    # Common OCR swaps in numeric contexts
    return (
        s.replace("O", "0")
        .replace("Q", "0")
        .replace("D", "0")
        .replace("I", "1")
        .replace("L", "1")
        .replace("Z", "2")
        .replace("S", "5")
        .replace("B", "8")
    )


def _clean_mrz_line(line: str) -> str:
    line = _normalize_mrz_chars(line)
    return line.replace(" ", "").strip()


def _find_mrz_lines(raw_text: str) -> Optional[List[str]]:
    """
    Try to find two MRZ-like lines in OCR text.
    We take the last 2 lines that match the MRZ pattern.
    """
    candidates: List[str] = []

    for ln in (raw_text or "").splitlines():
        t = _normalize_mrz_chars(ln.strip())
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

    line1, line2 = (_normalize_mrz_chars(mrz_lines[0]), _normalize_mrz_chars(mrz_lines[1]))

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

        # Passport number is alphanumeric in many countries; OCR commonly confuses O/0.
        passport_no = _fix_mrz_numeric(line2[0:9]).replace("<", "").strip()
        nationality = line2[10:13]
        dob = _fix_mrz_numeric(line2[13:19])
        sex = line2[20]
        expiry = _fix_mrz_numeric(line2[21:27])
        personal_number = _fix_mrz_numeric(line2[28:42]).replace("<", "").strip()

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
    r"(?P<dob>[0-9OIQDLSZB]{6})[0-9OIQDLSZB][A-Z<]\s+"
    r"(?P<exp>[0-9OIQDLSZB]{6})"
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

        passport_no = _fix_mrz_numeric(m.group("pass"))
        nationality = m.group("nat")
        dob = _fix_mrz_numeric(m.group("dob"))      # YYMMDD
        expiry = _fix_mrz_numeric(m.group("exp"))   # YYMMDD

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
    2) If that fails, try fallback single-line pattern.
    """
    mrz_lines = _find_mrz_lines(raw_text)
    if mrz_lines:
        td3 = _parse_td3_from_lines(mrz_lines)
        if td3:
            return td3

    fallback = _parse_fallback_line2(raw_text)
    if fallback:
        return fallback

    return None


# ----------------------------------------------------------------------
# 3) STANDARDIZED OUTPUT WRAPPER (SAFE TO ADD; DOES NOT BREAK EXISTING)
# ----------------------------------------------------------------------

def parse_passport_mrz_standard(*, raw_text: str = "", fixed_text: str = "", local_path: Optional[str] = None) -> Dict[str, Any]:
    """Return MRZ parse results using the project-wide standardized schema.

    Preference order:
      1) PassportEye (image-based) if local_path is provided and library is available
      2) Text-based MRZ detection from (fixed_text + raw_text)
    """
    errors: List[str] = []

    combined = (fixed_text or "") + "\n" + (raw_text or "")
    combined = _normalize_mrz_chars(combined)

    mrz_data: Optional[Dict[str, Any]] = None
    route = "MRZ"

    if local_path:
        try:
            mrz_data = parse_passport_mrz(local_path)
        except Exception as e:
            errors.append(f"passporteye_error: {e}")

    if not mrz_data:
        try:
            mrz_data = parse_passport_mrz_from_text(combined)
        except Exception as e:
            errors.append(f"text_mrz_error: {e}")

    parsed = {
        "full_name": "",
        "id_no": "",
        "nationality": "",
        "dob": "",
        "expiry": "",
        "gender": "",
    }

    confidence = 0.0
    template = None

    if mrz_data:
        parsed["full_name"] = (mrz_data.get("full_name") or "").strip()
        parsed["id_no"] = (mrz_data.get("id_no") or "").strip()
        parsed["nationality"] = (mrz_data.get("nationality") or mrz_data.get("country") or "").strip()
        parsed["dob"] = (mrz_data.get("dob") or "").strip()
        parsed["expiry"] = (mrz_data.get("expiry") or "").strip()
        parsed["gender"] = (mrz_data.get("sex") or "").strip()
        confidence = float(mrz_data.get("confidence") or 0.0)
    else:
        errors.append("mrz_not_found")

    return {
        "raw_text": raw_text or "",
        "fixed_text": fixed_text or "",
        "parsed": parsed,
        "confidence": confidence,
        "route": route,
        "template": template,
        "errors": errors,
    }


def parse_passport_mrz_standard_text_only(raw_text: str, fixed_text: str = "") -> Dict[str, Any]:
    """Legacy helper: standard schema wrapper using *only* text-based MRZ."""
    combined = (raw_text or "") + "\n" + (fixed_text or "")
    errors: List[str] = []

    mrz = parse_passport_mrz_from_text(combined)
    if not mrz:
        return {
            "raw_text": raw_text or "",
            "fixed_text": fixed_text or "",
            "parsed": {
                "full_name": "",
                "id_no": "",
                "nationality": "",
                "dob": "",
                "expiry": "",
                "gender": "",
            },
            "confidence": 0.0,
            "route": "MRZ",
            "template": None,
            "errors": ["MRZ not detected in text"],
        }

    parsed = {
        "full_name": mrz.get("full_name") or "",
        "id_no": mrz.get("id_no") or "",
        "nationality": mrz.get("nationality") or mrz.get("country") or "",
        "dob": mrz.get("dob") or "",
        "expiry": mrz.get("expiry") or "",
        "gender": mrz.get("sex") or "",
    }
    conf = float(mrz.get("confidence") or 0.0)
    if not parsed["id_no"]:
        errors.append("MRZ parsed but passport number missing")
        conf = min(conf, 0.6)
    if not parsed["dob"] or not parsed["expiry"]:
        errors.append("MRZ parsed but DOB/expiry missing")
        conf = min(conf, 0.7)

    return {
        "raw_text": raw_text or "",
        "fixed_text": fixed_text or "",
        "parsed": parsed,
        "confidence": conf,
        "route": "MRZ",
        "template": None,
        "errors": errors,
    }
