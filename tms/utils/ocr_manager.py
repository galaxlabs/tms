# /home/xg/xg-b/apps/tms/tms/utils/ocr_manager.py
# tms/utils/ocr_manager.py
# tms/utils/ocr_manager.py
import os
import re
import json
from pathlib import Path
import frappe

from tms.utils.gemini_extract import gemini_extract_identity_fields


class OCRManager:
    def __init__(self):
        self.ocr_history = []

    def _engine_from_conf(self) -> str:
        value = (frappe.conf.get("ocr_engine") or "gvision").lower()
        if value not in {"gvision", "tesseract", "auto"}:
            value = "gvision"
        return value

    def get_file_path(self, file_url: str) -> str:
        if not file_url:
            return ""
        name = Path(file_url).name
        if file_url.startswith("/private/"):
            return frappe.get_site_path("private", "files", name)
        return frappe.get_site_path("public", "files", name)

    def _run_gvision(self, file_path: str) -> str:
        from google.cloud import vision
        from google.oauth2 import service_account

        key_path = frappe.conf.get("google_vision_key_path")
        if not key_path or not os.path.exists(key_path):
            raise RuntimeError(f"google_vision_key_path missing or not found: {key_path}")

        creds = service_account.Credentials.from_service_account_file(key_path)
        client = vision.ImageAnnotatorClient(credentials=creds)

        with open(file_path, "rb") as f:
            content = f.read()

        image = vision.Image(content=content)
        response = client.text_detection(image=image)

        if response.error.message:
            raise RuntimeError(response.error.message)

        texts = response.text_annotations
        if not texts:
            return ""
        return texts[0].description or ""

    def _run_tesseract(self, file_path: str) -> str:
        from PIL import Image
        import pytesseract

        img = Image.open(file_path)
        try:
            img = img.convert("L")
        except Exception:
            pass

        config = "--oem 3 --psm 6 -c preserve_interword_spaces=1"
        text = pytesseract.image_to_string(img, lang="eng+ara", config=config)
        return (text or "").strip()

    def extract_raw_text(self, file_url: str) -> tuple[str, str]:
        file_path = self.get_file_path(file_url)
        if not file_path or not os.path.exists(file_path):
            frappe.log_error(f"OCR file not found: {file_path}", "OCRManager")
            return "", "none"

        engine_pref = self._engine_from_conf()
        raw_text = ""
        engine_used = "none"

        if engine_pref == "gvision":
            try:
                raw_text = self._run_gvision(file_path)
                engine_used = "gvision"
            except Exception:
                frappe.log_error(frappe.get_traceback(), "Google Vision OCR failed")

        elif engine_pref == "tesseract":
            try:
                raw_text = self._run_tesseract(file_path)
                engine_used = "tesseract"
            except Exception:
                frappe.log_error(frappe.get_traceback(), "Tesseract OCR failed")

        elif engine_pref == "auto":
            try:
                raw_text = self._run_gvision(file_path)
                engine_used = "gvision"
            except Exception:
                raw_text = ""
            if not raw_text:
                try:
                    raw_text = self._run_tesseract(file_path)
                    engine_used = "tesseract"
                except Exception:
                    frappe.log_error(frappe.get_traceback(), "Tesseract OCR failed (auto)")

        return (raw_text or "").strip(), engine_used


# ---------------------------
# Validators / cleaners
# ---------------------------

_DATE_LIKE = re.compile(r"^\s*\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\s*$")
_MOSTLY_DIGITS = re.compile(r"^\s*[\d\s\-\/]+\s*$")

def _clean_name(x: str) -> str:
    x = (x or "").strip()
    x = re.sub(r"\s+", " ", x)
    # kill obvious junk
    if not x or len(x) < 3:
        return ""
    if x.lower() in {"ksa", "ksaksa", "saudi", "saudi arabia"}:
        return ""
    return x

def _clean_id(x: str) -> str:
    x = (x or "").strip()
    x = x.replace(" ", "").replace("-", "")
    # common OCR junk
    x = x.replace("O", "0") if x.isupper() else x
    if not x:
        return ""
    # Accept passport/id: 6-20 chars alnum
    if re.fullmatch(r"[A-Za-z0-9]{6,20}", x):
        return x
    # Accept pure digits (iqama) 8-15 digits
    if re.fullmatch(r"\d{8,15}", x):
        return x
    return ""

def _clean_nationality(x: str) -> str:
    x = (x or "").strip()
    x = re.sub(r"\s+", " ", x)
    if not x:
        return ""
    # if it looks like date or mostly numbers => wrong
    if _DATE_LIKE.match(x) or _MOSTLY_DIGITS.match(x):
        return ""
    # too short or junk
    if len(x) < 3:
        return ""
    return x


# ----------------------------------------------------------------------
# MODULE-LEVEL FUNCTION (this is what your WhatsApp bot imports)
# ----------------------------------------------------------------------

def analyze_id_document(file_url: str) -> dict:
    """
    Unified OCR -> Gemini extraction -> validated fields.

    Returns exactly what your WhatsApp bot expects:
    {
      full_name, id_no, nationality, raw_text, fixed_text, confidence, engine, json_data
    }
    """
    mgr = OCRManager()
    raw_text, ocr_engine = mgr.extract_raw_text(file_url)

    # Gemini extraction from OCR text (NOT from image)
    gem = {}
    try:
        gem = gemini_extract_identity_fields(
            ocr_text=raw_text or "",
            hint=(
                "Extract passenger identity fields from OCR text.\n"
                "Return ONLY JSON with keys: full_name, id_no, nationality, doc_type, confidence.\n"
                "Nationality must be a country name, NOT date-of-birth.\n"
                "id_no must be passport number or iqama id.\n"
            ),
        ) or {}
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Gemini extract failed")
        gem = {}

    # Clean / validate outputs
    full_name = _clean_name(gem.get("full_name") or "")
    id_no = _clean_id(gem.get("id_no") or "")
    nationality = _clean_nationality(gem.get("nationality") or "")

    # If gemini missed id_no, try a small regex fallback from raw_text
    if not id_no and raw_text:
        # Example patterns (you can extend later)
        m = re.search(r"\b([A-Z0-9]{7,12})\b", raw_text.upper())
        if m:
            id_no = _clean_id(m.group(1))

    # Confidence
    confidence = int(gem.get("confidence") or 0)
    if full_name:
        confidence = max(confidence, 50)
    if full_name and id_no:
        confidence = max(confidence, 70)

    return {
        "full_name": full_name,
        "id_no": id_no,
        "nationality": nationality,
        "raw_text": raw_text or "",
        "fixed_text": raw_text or "",
        "confidence": confidence,
        "engine": f"{ocr_engine}+gemini",
        "json_data": {
            "ocr_engine": ocr_engine,
            "gemini": gem,
        },
    }




# import os
# from pathlib import Path
# from tms.utils.gemini_extract import gemini_extract_identity_fields
# import frappe


# class OCRManager:
#     def __init__(self):
#         # Just keep a simple in-memory history for debugging/stats
#         self.ocr_history = []

#     # ------------------------------------------------------------------
#     # Engine selection + file path
#     # ------------------------------------------------------------------

#     def _engine_from_conf(self) -> str:
#         """
#         Read frappe.conf.ocr_engine and normalise.
#         Allowed values: gvision, tesseract, auto
#         Default: gvision
#         """
#         value = (frappe.conf.get("ocr_engine") or "gvision").lower()
#         if value not in {"gvision", "tesseract", "auto"}:
#             value = "gvision"
#         return value

#     def get_file_path(self, file_url: str) -> str:
#         """Convert /files/xxx.jpg or /private/files/xxx.jpg to full path."""
#         if not file_url:
#             return ""

#         name = Path(file_url).name

#         if file_url.startswith("/private/"):
#             return frappe.get_site_path("private", "files", name)
#         else:
#             return frappe.get_site_path("public", "files", name)

#     # ------------------------------------------------------------------
#     # Engines
#     # ------------------------------------------------------------------

#     def _run_gvision(self, file_path: str) -> str:
#         """OCR using Google Cloud Vision."""
#         from google.cloud import vision
#         from google.oauth2 import service_account

#         key_path = frappe.conf.get("google_vision_key_path")
#         if not key_path or not os.path.exists(key_path):
#             raise RuntimeError(
#                 f"google_vision_key_path missing or not found: {key_path}"
#             )

#         creds = service_account.Credentials.from_service_account_file(key_path)
#         client = vision.ImageAnnotatorClient(credentials=creds)

#         with open(file_path, "rb") as f:
#             content = f.read()

#         image = vision.Image(content=content)
#         response = client.text_detection(image=image)

#         if response.error.message:
#             raise RuntimeError(response.error.message)

#         texts = response.text_annotations
#         if not texts:
#             return ""

#         # texts[0] is the full text block
#         return texts[0].description or ""

#     def _run_tesseract(self, file_path: str) -> str:
#         """Simple local Tesseract using only PIL + pytesseract (no cv2)."""
#         from PIL import Image
#         import pytesseract

#         img = Image.open(file_path)
#         try:
#             img = img.convert("L")  # grayscale
#         except Exception:
#             pass

#         config = "--oem 3 --psm 6 -c preserve_interword_spaces=1"
#         text = pytesseract.image_to_string(img, lang="eng+ara", config=config)
#         return (text or "").strip()

#     # ------------------------------------------------------------------
#     # Main entry
#     # ------------------------------------------------------------------

#     def extract_from_image(self, file_url: str) -> dict:
#         """
#         Main OCR call.

#         Returns:
#         {
#           "raw_text": "...",
#           "structured_data": {
#               "name": "...",
#               "id_no": "...",
#               "nationality": "...",
#               "confidence": 0-100
#           },
#           "ocr_engine": "gvision" | "tesseract" | "none"
#         }
#         """
#         from tms.utils.parser import parse_passenger_details

#         file_path = self.get_file_path(file_url)

#         if not file_path or not os.path.exists(file_path):
#             frappe.log_error(f"OCR file not found: {file_path}", "OCRManager")
#             return {
#                 "raw_text": "",
#                 "structured_data": {
#                     "name": "",
#                     "id_no": "",
#                     "nationality": "",
#                     "confidence": 0,
#                 },
#                 "ocr_engine": "none",
#             }

#         engine_pref = self._engine_from_conf()
#         raw_text = ""
#         engine_used = "none"

#         # 1) Choose engine
#         if engine_pref == "gvision":
#             try:
#                 raw_text = self._run_gvision(file_path)
#                 engine_used = "gvision"
#             except Exception as e:
#                 frappe.log_error(
#                     "Google Vision OCR failed",
#                     f"Google Vision OCR failed: {e}",
#                 )

#         elif engine_pref == "tesseract":
#             try:
#                 raw_text = self._run_tesseract(file_path)
#                 engine_used = "tesseract"
#             except Exception as e:
#                 frappe.log_error(
#                     "Tesseract OCR failed",
#                     f"Tesseract OCR failed: {e}",
#                 )

#         elif engine_pref == "auto":
#             # Try Google Vision first
#             try:
#                 raw_text = self._run_gvision(file_path)
#                 engine_used = "gvision"
#             except Exception as e:
#                 frappe.log_error(
#                     "Google Vision OCR failed (auto)",
#                     f"Google Vision OCR failed (auto): {e}",
#                 )
#                 raw_text = ""

#             # Fallback to Tesseract if Vision returns nothing / fails
#             if not raw_text:
#                 try:
#                     raw_text = self._run_tesseract(file_path)
#                     engine_used = "tesseract"
#                 except Exception as e:
#                     frappe.log_error(
#                         "Tesseract OCR failed (auto)",
#                         f"Tesseract OCR failed (auto): {e}",
#                     )

#         # 2) If still nothing, return empty structured block
#         if not raw_text:
#             structured = {
#                 "name": "",
#                 "id_no": "",
#                 "nationality": "",
#                 "confidence": 0,
#             }
#         else:
#             # Parse to name / id / nationality
#             try:
#                 parsed = parse_passenger_details(raw_text, raw_text) or {}
#             except Exception as e:
#                 frappe.log_error(
#                     "parse_passenger_details failed",
#                     f"parse_passenger_details failed: {e}",
#                 )
#                 parsed = {}

#             name = (parsed.get("name") or "").strip()
#             id_no = (parsed.get("id_no") or "").strip()
#             nationality = (parsed.get("nationality") or "").strip()

#             confidence = 0
#             if name:
#                 confidence += 40
#             if id_no:
#                 confidence += 40
#             if nationality:
#                 confidence += 20

#             structured = {
#                 "name": name,
#                 "id_no": id_no,
#                 "nationality": nationality,
#                 "confidence": min(confidence, 100),
#             }

#         # History in memory (useful if you later add a UI or stats)
#         self.ocr_history.append(
#             {
#                 "file_url": file_url,
#                 "raw_text": raw_text,
#                 "extracted_data": structured,
#                 "engine": engine_used,
#                 "timestamp": frappe.utils.now(),
#             }
#         )

#         return {
#             "raw_text": raw_text,
#             "structured_data": structured,
#             "ocr_engine": engine_used,
#         }


# # ----------------------------------------------------------------------
# # Helper used by WhatsApp bot / other code
# # ----------------------------------------------------------------------

# # inside tms/utils/ocr_manager.py


#     def analyze_id_document(file_url: str) -> dict:
#         # 1) your existing OCR step -> raw_text, fixed_text, confidence
#         # raw_text = ...
#         # fixed_text = ...
#         # confidence = ...

#         # 2) Use Gemini to extract stable fields from OCR text
#         gem = gemini_extract_identity_fields(
#             ocr_text=fixed_text or raw_text or "",
#             hint="Extract passenger details for Trip. Fields needed: full_name, id_no(passport/iqama), nationality(country)."
#         )

#         # 3) Build unified result (what your bot expects)
#         return {
#             "full_name": gem.get("full_name") or "",
#             "id_no": gem.get("id_no") or "",
#             "nationality": gem.get("nationality") or "",
#             "raw_text": raw_text or "",
#             "fixed_text": fixed_text or "",
#             "confidence": gem.get("confidence") or confidence or 0,
#             "json_data": {
#                 "doc_type": gem.get("doc_type"),
#                 "gemini_debug": gem.get("debug", {}),
#             }
#         }

# def analyze_id_document(
#     file_url: str,
#     document_type: str | None = None,
#     country: str | None = None,
#     use_llm_refinement: bool = True,
#     min_confidence_for_llm: int = 70,
# ) -> dict:
    """
    Unified OCR + learning API.

    Returns:
    {
        "full_name": "...",
        "id_no": "...",
        "nationality": "...",
        "raw_text": "...",
        "fixed_text": "...",
        "confidence": 0-100,
        "engine": "gvision|openai|llm",
        "json_data": {...}
    }
    """
    from tms.utils.ocr_learning import refine_with_llm  # lazy import

    mgr = OCRManager()
    base = mgr.extract_from_image(file_url)

    raw_text = base.get("raw_text") or ""
    structured = base.get("structured_data") or {}
    engine = base.get("ocr_engine") or "unknown"

    name = (structured.get("name") or "").strip()
    id_no = (structured.get("id_no") or "").strip()
    nationality = (structured.get("nationality") or "").strip()
    confidence = int(structured.get("confidence") or 0)

    # Fallback country & doc type
    if not country and nationality:
        country = nationality
    if not document_type:
        document_type = "Passport"  # safe default; you can change per-context

    # Decide whether to call LLM refinement
    refined = None
    if use_llm_refinement and (confidence < min_confidence_for_llm or not (name and id_no)):
        try:
            refined = refine_with_llm(raw_text, document_type=document_type, country=country)
        except Exception as e:
            frappe.log_error(f"LLM refinement call failed: {e}", "analyze_id_document")

    if refined and refined.get("confidence", 0) > confidence:
        name = refined.get("full_name") or name
        id_no = refined.get("id_no") or id_no
        nationality = refined.get("nationality") or nationality
        confidence = refined.get("confidence", confidence)
        engine = refined.get("engine", engine)

    json_data = {
        "base_structured": structured,
        "llm_refined": refined,
    }

    return {
        "full_name": name,
        "id_no": id_no,
        "nationality": nationality,
        "raw_text": raw_text,
        "fixed_text": raw_text,  # you can add Arabic reshaping later
        "confidence": confidence,
        "engine": engine,
        "json_data": json_data,
    }