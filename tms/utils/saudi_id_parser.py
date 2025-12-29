# tms/tms/utils/saudi_id_parser.py
from __future__ import annotations

from typing import Optional, Dict, Any, List
import re
import unicodedata

# Optional external validator
try:
    from saudi_id_validator import is_valid_saudi_id  # type: ignore
except Exception:
    is_valid_saudi_id = None

ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

# Starts with 1 or 2; 10 digits total
SAUDI_ID_STRICT_RE = re.compile(r"(?<!\d)([12]\d{9})(?!\d)")
# Spaced/fragmented version: 1 0 2 3 4 5 6 7 8 9 (allow spaces)
SAUDI_ID_SPACED_RE = re.compile(r"(?<!\d)([12](?:\s*\d){9})(?!\d)")

# English name line: usually all caps + spaces, 3+ words
EN_NAME_LINE_RE = re.compile(r"^[A-Z][A-Z \-'.]{10,}$")

# DOB patterns (we’ll normalize Arabic digits first)
DOB_RE_LIST = [
    re.compile(r"(\d{4})[\/\-.](\d{1,2})[\/\-.](\d{1,2})"),  # YYYY/MM/DD
    re.compile(r"(\d{1,2})[\/\-.](\d{1,2})[\/\-.](\d{4})"),  # DD/MM/YYYY
]


def _normalize_text(text: str) -> str:
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", text)
    t = t.replace("\u200e", "").replace("\u200f", "")
    return t.translate(ARABIC_DIGITS)


def _split_lines(text: str) -> List[str]:
    return [ln.strip() for ln in (text or "").splitlines() if ln.strip()]


def _contains_any(line: str, anchors: List[str]) -> bool:
    low = (line or "").lower()
    for a in anchors:
        if a.lower() in low:
            return True
    return False


def _extract_after_anchor(lines: List[str], anchors: List[str]) -> Optional[str]:
    """
    Finds value after an anchor:
      - same line after ':', '-', '.', '—', '–'
      - or on the next line
    """
    for i, ln in enumerate(lines):
        if not _contains_any(ln, anchors):
            continue

        parts = re.split(r"[:\-–—\.]+", ln, maxsplit=1)
        if len(parts) == 2 and parts[1].strip():
            return parts[1].strip()

        if i + 1 < len(lines):
            nxt = lines[i + 1].strip()
            if nxt:
                return nxt
    return None


def _fallback_is_valid_saudi_id(id_no: str) -> bool:
    """Check-digit validation for 10-digit Saudi ID/Iqama."""
    if not id_no or not re.fullmatch(r"[12]\d{9}", id_no):
        return False
    total = 0
    for i, ch in enumerate(id_no):
        d = ord(ch) - 48
        if (i % 2) == 0:
            x = d * 2
            total += (x // 10) + (x % 10)
        else:
            total += d
    return (total % 10) == 0


def _validate_saudi_id(id_no: str) -> bool:
    try:
        if is_valid_saudi_id is not None:
            return bool(is_valid_saudi_id(id_no))
    except Exception:
        pass
    return _fallback_is_valid_saudi_id(id_no)


def _clean_spaced_id(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def _extract_id_after_anchor(lines: List[str]) -> Optional[str]:
    """
    Extract PRIMARY ID (رقم الهوية / Iqama No) ONLY by searching near the anchor.
    Prevents picking employer ID or other 10-digit numbers elsewhere.
    """
    anchors_primary = [
        "رقم الهوية",
        "رقم الهويه",
        "رقم هوية",
        "رقم الإقامة",
        "رقم الاقامة",
        "رقم الإقامه",
        "iqama no",
        "iqama",
        "id no",
        "identity no",
    ]

    # OCR sometimes shows it reversed/with dots like ".ةيوهلا رقم"
    anchor_variants = [
        ".ةيوهلا رقم",
        "ةيوهلا رقم",
        "الهوية رقم",
        "رقم. الهوية",
        "رقم الهوية.",
    ]

    def is_anchor_line(ln: str) -> bool:
        low = (ln or "").lower()
        if any(a in low for a in anchors_primary):
            return True
        if any(v in (ln or "") for v in anchor_variants):
            return True
        return False

    for i, ln in enumerate(lines):
        if not is_anchor_line(ln):
            continue

        # Search in this line + next 3 lines (your sample has anchor then DOB/nationality lines)
        window = " ".join(lines[i : min(i + 4, len(lines))])

        for m in SAUDI_ID_STRICT_RE.findall(window):
            if _validate_saudi_id(m):
                return m

        for m in SAUDI_ID_SPACED_RE.findall(window):
            cand = _clean_spaced_id(m)
            if _validate_saudi_id(cand):
                return cand

    return None


def _pick_best_english_name(lines: List[str]) -> str:
    """
    Choose best ALL-CAPS name line (e.g. 'MOHAMMAD SHOHEL DULAL MIAH').
    Reject lines that contain Arabic label words or obvious OCR junk.
    """
    bad_keywords = [
        "رقم", "هوية", "الهويه", "الإقامة", "الاقامة",
        "تاريخ", "الانتهاء", "الميلاد", "الجنسية", "الديانة",
    ]

    best = ""
    best_score = -1

    for ln in lines:
        if any(k in ln for k in bad_keywords):
            continue

        s = (ln or "").upper().strip()
        s_clean = re.sub(r"[^A-Z \-'.]", " ", s)
        s_clean = re.sub(r"\s+", " ", s_clean).strip()
        if not s_clean:
            continue

        if not EN_NAME_LINE_RE.match(s_clean):
            continue

        words = [w for w in s_clean.split() if len(w) >= 2]
        if len(words) < 3:
            continue

        tiny = [w for w in s_clean.split() if len(w) <= 2]
        if len(tiny) >= 3:
            continue

        score = (len(words) * 10) + len(s_clean)
        if score > best_score:
            best_score = score
            best = s_clean

    return best


def _extract_nationality(lines: List[str]) -> str:
    val = _extract_after_anchor(lines, ["الجنسية", "Nationality"])
    if val:
        val = re.split(r"(?:الديانة|Religion)", val, maxsplit=1)[0].strip()
        parts = val.split()
        if parts:
            return " ".join(parts[:3]).strip()

    for ln in lines:
        if "بنجلاديش" in ln:
            return "بنجلاديش"
        if "بتجلاديش" in ln:
            return "بتجلاديش"

    return ""


def _extract_dob(lines: List[str]) -> str:
    anchors = ["تاريخ الميلاد", "الميلاد", "Date of Birth", "DOB"]

    for i, ln in enumerate(lines):
        if not _contains_any(ln, anchors):
            continue

        hay = ln
        if i + 1 < len(lines):
            hay += " " + lines[i + 1]

        for rx in DOB_RE_LIST:
            m = rx.search(hay)
            if not m:
                continue

            g = m.groups()
            if len(g[0]) == 4:
                y, mo, d = int(g[0]), int(g[1]), int(g[2])
            else:
                d, mo, y = int(g[0]), int(g[1]), int(g[2])

            if 1900 <= y <= 2100 and 1 <= mo <= 12 and 1 <= d <= 31:
                return f"{y:04d}-{mo:02d}-{d:02d}"

    all_text = " ".join(lines)
    for rx in DOB_RE_LIST:
        m = rx.search(all_text)
        if not m:
            continue
        g = m.groups()
        if len(g[0]) == 4:
            y, mo, d = int(g[0]), int(g[1]), int(g[2])
            if 1900 <= y <= 2100 and 1 <= mo <= 12 and 1 <= d <= 31:
                return f"{y:04d}-{mo:02d}-{d:02d}"

    return ""


def parse_saudi_id_from_text(raw_text: str) -> Dict[str, Any]:
    raw_text = _normalize_text(raw_text or "")
    lines = _split_lines(raw_text)

    # ID: ANCHOR ONLY (avoid wrong IDs like employer ID)
    id_no = _extract_id_after_anchor(lines)

    # Name
    full_name = _pick_best_english_name(lines)
    if not full_name:
        anchored = _extract_after_anchor(lines, ["الاسم", "اسم حامل البطاقة"])
        full_name = anchored or ""

    # Nationality / DOB
    nationality = _extract_nationality(lines)
    dob = _extract_dob(lines)

    # Confidence
    confidence = 0.0
    errors: List[str] = []

    if id_no:
        confidence += 0.75
    else:
        errors.append("id_not_found")

    if full_name:
        confidence += 0.15
    else:
        errors.append("name_not_found")

    if nationality:
        confidence += 0.07
    else:
        errors.append("nationality_not_found")

    if dob:
        confidence += 0.03

    confidence = max(0.0, min(1.0, confidence))

    return {
        "engine": "saudi_id_parser",
        "id_no": id_no,
        "full_name": full_name,
        "nationality": nationality,
        "dob": dob,
        "confidence": confidence,
        "errors": errors,
    }

def parse_saudi_id_standard(raw_text: str = "", fixed_text: str = "", digits_text: str = "") -> Dict[str, Any]:
    """
    Standard schema wrapper.

    digits_text: optional extra OCR text from a digits-only OCR pass.
    """
    helper = ""
    if digits_text and digits_text.strip():
        # Make digits appear near the anchor so anchor-based extractor can find it
        helper = f"\nرقم الهوية {digits_text}\n.ةيوهلا رقم {digits_text}\n"

    combined = _normalize_text((fixed_text or "") + "\n" + (raw_text or "") + helper + "\n" + (digits_text or ""))
    out = parse_saudi_id_from_text(combined)

    parsed = {
        "full_name": (out.get("full_name") or "").strip(),
        "id_no": (out.get("id_no") or "").strip(),
        "nationality": (out.get("nationality") or "").strip(),
        "dob": (out.get("dob") or "").strip(),
        "expiry": "",
        "gender": "",
    }

    return {
        "raw_text": raw_text or "",
        "fixed_text": fixed_text or "",
        "parsed": parsed,
        "confidence": float(out.get("confidence") or 0.0),
        "route": "Regex",
        "template": None,
        "errors": list(out.get("errors") or []),
    }

# def parse_saudi_id_standard(raw_text: str = "", fixed_text: str = "", digits_text: str = "") -> Dict[str, Any]:
#     """
#     Standard schema wrapper.

#     digits_text: optional extra OCR text from a digits-only OCR pass.
#     """
#     combined = _normalize_text((fixed_text or "") + "\n" + (raw_text or "") + "\n" + (digits_text or ""))
#     out = parse_saudi_id_from_text(combined)

#     parsed = {
#         "full_name": (out.get("full_name") or "").strip(),
#         "id_no": (out.get("id_no") or "").strip(),
#         "nationality": (out.get("nationality") or "").strip(),
#         "dob": (out.get("dob") or "").strip(),
#         "expiry": "",
#         "gender": "",
#     }

#     return {
#         "raw_text": raw_text or "",
#         "fixed_text": fixed_text or "",
#         "parsed": parsed,
#         "confidence": float(out.get("confidence") or 0.0),
#         "route": "Regex",
#         "template": None,
#         "errors": list(out.get("errors") or []),
#     }
