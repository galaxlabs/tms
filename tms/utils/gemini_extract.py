# tms/utils/gemini_extract.py
import json
import re
import requests
import frappe
import os
import base64
import mimetypes

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"  # Gemini Developer API
DEFAULT_MODEL = "gemini-2.5-flash"  # fast + good enough for extraction

DATE_LIKE = re.compile(r"\b(\d{1,2}[-/ ]\d{1,2}[-/ ]\d{2,4}|\d{4}[-/]\d{1,2}[-/]\d{1,2})\b")
DIGITS_HEAVY = re.compile(r"^\W*(\d[\d\W]*){6,}\W*$")


def _get_gemini_key() -> str:
    # You have Single DocType "Google Gimni"
    s = frappe.get_single("Google Gimni")
    key = (s.api_key or "").strip()
    if not key:
        frappe.throw("Google Gimni API key missing in Google Gimni doctype")
    return key


def _clean_country(value: str) -> str:
    if not value:
        return ""
    v = value.strip()

    # if Gemini mistakenly returns DOB or number as nationality
    if DATE_LIKE.search(v) or DIGITS_HEAVY.match(v):
        return ""
    # remove common OCR junk
    v = re.sub(r"[^A-Za-z\u0600-\u06FF \-]", " ", v)
    v = re.sub(r"\s+", " ", v).strip()
    return v


def _clean_name(value: str) -> str:
    if not value:
        return ""
    v = value.strip()
    # kill very short garbage
    if len(v) < 3:
        return ""
    # remove obvious junk tokens
    v = re.sub(r"\b(ksa|ksaksa|saudi|arabia)\b", "", v, flags=re.I)
    v = re.sub(r"\s+", " ", v).strip()
    return v


def _clean_id(value: str) -> str:
    if not value:
        return ""
    v = value.strip()
    # keep letters/digits only (passport can be alnum)
    v = re.sub(r"[^A-Za-z0-9]", "", v)
    if len(v) < 5:
        return ""
    return v


def gemini_extract_identity_fields(ocr_text: str, hint: str = "") -> dict:
    """
    Input: OCR text (messy)
    Output: dict with:
      full_name, id_no, nationality, doc_type, confidence, debug
    """

    key = _get_gemini_key()
    model = frappe.conf.get("google_gemini_model") or DEFAULT_MODEL

    system = (
        "You are a strict information extraction engine for travel documents.\n"
        "Extract passenger identity from OCR text of: PASSPORT or IQAMA or VISA paper.\n"
        "Return ONLY valid JSON (no markdown)."
    )

    # IMPORTANT: strict JSON schema + strong rules to stop DOB becoming nationality
    prompt = {
        "task": "extract_passenger_identity",
        "rules": [
            "Return ONLY JSON object. No extra keys.",
            "full_name must be the person's name (not country, not random tokens).",
            "id_no must be Passport number OR Iqama ID (choose the best available).",
            "nationality must be a country name (e.g., Pakistan, India, Egypt). Not DOB. Not dates. Not numbers.",
            "If a field is unknown, return empty string.",
            "confidence is 0-100 (how sure you are overall)."
        ],
        "hint": hint or "",
        "ocr_text": ocr_text[:12000]  # keep within safe size
    }

    url = f"{GEMINI_BASE}/models/{model}:generateContent"
    params = {"key": key}
    payload = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": json.dumps(prompt, ensure_ascii=False)}]}],
        "generationConfig": {
            "temperature": 0.1,
            "topP": 0.9,
            "maxOutputTokens": 512,
            "responseMimeType": "application/json"
        },
    }

    r = requests.post(url, params=params, json=payload, timeout=35)
    try:
        data = r.json()
    except Exception:
        return {"full_name": "", "id_no": "", "nationality": "", "doc_type": "", "confidence": 0, "debug": {"http": r.status_code, "text": r.text}}

    if r.status_code != 200:
        return {"full_name": "", "id_no": "", "nationality": "", "doc_type": "", "confidence": 0, "debug": data}

    # Gemini response text:
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        obj = json.loads(text)
    except Exception:
        return {"full_name": "", "id_no": "", "nationality": "", "doc_type": "", "confidence": 0, "debug": data}

    # sanitize
    full_name = _clean_name(obj.get("full_name", ""))
    id_no = _clean_id(obj.get("id_no", ""))
    nationality = _clean_country(obj.get("nationality", ""))
    doc_type = (obj.get("doc_type") or "").strip()
    confidence = int(obj.get("confidence") or 0)

    return {
        "full_name": full_name,
        "id_no": id_no,
        "nationality": nationality,
        "doc_type": doc_type,
        "confidence": confidence,
        "debug": {"model": model}
    }


def extract_vat_invoice_with_gemini(ocr_text: str, hint: str = "") -> dict:
    """
    Extract VAT invoice parties, dates, totals, and simple line items from OCR text.
    """

    key = _get_gemini_key()
    model = frappe.conf.get("google_gemini_model") or DEFAULT_MODEL

    system = (
        "You are a strict VAT invoice extraction engine.\n"
        "Read OCR text from Arabic/English invoices and return ONLY valid JSON.\n"
        "Focus on issuer details, customer details, invoice reference, dates, VAT rate, totals, and items."
    )

    prompt = {
        "task": "extract_vat_invoice",
        "rules": [
            "Return ONLY JSON object. No markdown.",
            "issuer_* fields belong to the company that issued the invoice/letterhead.",
            "document_customer_* fields belong to the customer shown on the invoice.",
            "invoice_date must use YYYY-MM-DD when possible.",
            "process_type_hint must be Sales, Purchase, or empty string.",
            "vat_rate is numeric only.",
            "items must be a JSON array of rows with item_text, qty, rate, vat_rate.",
            "If a value is unknown, return empty string or 0.",
        ],
        "hint": hint or "",
        "ocr_text": (ocr_text or "")[:16000],
    }

    url = f"{GEMINI_BASE}/models/{model}:generateContent"
    params = {"key": key}
    payload = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": json.dumps(prompt, ensure_ascii=False)}]}],
        "generationConfig": {
            "temperature": 0.1,
            "topP": 0.9,
            "maxOutputTokens": 1536,
            "responseMimeType": "application/json",
        },
    }

    try:
        response = requests.post(url, params=params, json=payload, timeout=45)
        data = response.json()
    except Exception as exc:
        frappe.log_error(frappe.get_traceback(), "Gemini VAT Invoice Extraction Failed")
        return {"confidence": 0, "error": str(exc)}

    if response.status_code != 200:
        frappe.log_error(json.dumps(data, ensure_ascii=False), "Gemini VAT Invoice Extraction Error")
        return {"confidence": 0, "error": data}

    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        result = json.loads(text)
    except Exception:
        frappe.log_error(json.dumps(data, ensure_ascii=False), "Gemini VAT Invoice JSON Parse Failed")
        return {"confidence": 0, "error": data}

    result["issuer_name_text"] = _clean_name(result.get("issuer_name_text", ""))
    result["document_customer_name_text"] = _clean_name(result.get("document_customer_name_text", ""))
    result["issuer_vat_no"] = _clean_id(result.get("issuer_vat_no", ""))
    result["document_customer_vat_no"] = _clean_id(result.get("document_customer_vat_no", ""))
    result["external_invoice_no"] = _clean_id(result.get("external_invoice_no", ""))
    result["confidence"] = int(result.get("confidence") or 0)
    result["vat_rate"] = float(result.get("vat_rate") or 0)
    result["items"] = result.get("items") if isinstance(result.get("items"), list) else []
    result["debug"] = {"model": model}
    return result

def gemini_extract_from_file_url(file_url: str) -> dict:
    """
    Direct vision extraction: send file bytes to Gemini and return stable JSON.
    """
    api_key = _get_gemini_key()
    file_bytes, mime = _file_url_to_bytes(file_url)

    # ---- Gemini REST call ----
    import requests

    b64 = base64.b64encode(file_bytes).decode("utf-8")

    prompt = """
Return ONLY JSON. No markdown. No extra text.

Extract passenger identity fields from this document image/PDF.
Rules:
- full_name: person name exactly as document
- id_no: passport number or iqama/id number (no spaces)
- nationality: country name ONLY (not date of birth)
If missing, return empty string.

JSON format:
{
  "full_name": "",
  "id_no": "",
  "nationality": "",
  "doc_type": "passport|iqama|visa|unknown",
  "confidence": 0
}
"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent?key={api_key}"

    payload = {
        "contents": [{
            "role": "user",
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": mime, "data": b64}}
            ]
        }],
        "generationConfig": {
            "temperature": 0,
            "topP": 0.1,
            "maxOutputTokens": 512
        }
    }

    r = requests.post(url, json=payload, timeout=60)
    data = r.json()

    # Gemini returns text in candidates[0].content.parts[0].text
    txt = ""
    try:
        txt = data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        frappe.log_error(json.dumps(data, indent=2), "Gemini Response Parse Failed")
        return {"full_name": "", "id_no": "", "nationality": "", "doc_type": "unknown", "confidence": 0}

    # parse strict json
    try:
        return json.loads(txt)
    except Exception:
        frappe.log_error(f"Gemini returned non-JSON:\n{txt}", "Gemini Non-JSON Output")
        return {"full_name": "", "id_no": "", "nationality": "", "doc_type": "unknown", "confidence": 0}
