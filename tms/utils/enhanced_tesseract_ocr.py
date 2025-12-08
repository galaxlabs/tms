# apps/tms/tms/utils/enhanced_tesseract_ocr.py

import frappe
import pytesseract
from PIL import Image
import json
import re
import unicodedata
from pathlib import Path

# --- small helpers (reuse your existing ideas) ---

AR_COUNTRY_MAP = {
    "مصر": "Egypt",
    "السعودية": "Saudi Arabia",
    "المملكة العربية السعودية": "Saudi Arabia",
    "باكستان": "Pakistan",
    "الهند": "India",
    "اليمن": "Yemen",
    "السودان": "Sudan",
    "سوريا": "Syria",
    "الأردن": "Jordan",
    "فلسطين": "Palestine",
    "بنغلاديش": "Bangladesh",
    "نيبال": "Nepal",
}

ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def normalize_text(text: str) -> str:
    """Remove direction markers and normalize Arabic digits."""
    text = unicodedata.normalize("NFKC", text or "")
    text = text.replace("\u200e", "").replace("\u200f", "")
    text = text.translate(ARABIC_DIGITS)
    return text


class EnhancedTesseractOCR:
    """
    Simplified OCR:
      - NO cv2
      - NO numpy
      - Just PIL + pytesseract
      - Parsing delegated to your existing parser.py
    """

    def __init__(self):
        # keep a very small learning structure so OCRManager.get_learning_stats() doesn't break
        self.learning_data = {
            "name_patterns": [],
            "id_patterns": [],
            "nationality_patterns": [],
            "corrections": {},
            "document_templates": {},
        }

    # ------------------------------------------------------------------
    # LOW LEVEL: text extraction
    # ------------------------------------------------------------------
    def _preprocess_image(self, image_path: str) -> Image.Image | None:
        """Very simple preprocessing with PIL only (robust)."""
        try:
            img = Image.open(image_path)

            # convert to grayscale
            img = img.convert("L")

            # optionally enlarge small images
            w, h = img.size
            if min(w, h) < 600:
                scale = 600 / min(w, h)
                img = img.resize(
                    (int(w * scale), int(h * scale)),
                    Image.Resampling.LANCZOS,
                )

            return img
        except Exception as e:
            frappe.log_error(f"PIL preprocess failed: {e}", "EnhancedTesseractOCR")
            return None

    def extract_text_with_tesseract(self, image_path: str) -> str:
        """
        Single, simple OCR call. No language auto-detect, just eng+ara.
        If this returns empty, we know the problem is Tesseract itself.
        """
        try:
            img = self._preprocess_image(image_path)
            if img is None:
                return ""

            config = "--oem 3 --psm 6 -c preserve_interword_spaces=1"
            # you can change lang to "eng" if arabic data is missing
            text = pytesseract.image_to_string(img, lang="eng+ara", config=config)

            # normalize digits, remove weird control chars
            text = normalize_text(text)
            return text.strip()
        except Exception as e:
            frappe.log_error(f"Simple Tesseract OCR failed: {e}", "EnhancedTesseractOCR")
            return ""

    # ------------------------------------------------------------------
    # STRUCTURED DATA
    # ------------------------------------------------------------------
    def extract_structured_data(self, text: str) -> dict:
        """
        Use your existing parser logic (parser.py) to get:
          - name
          - id_no
          - nationality
        """
        try:
            from tms.utils.parser import parse_passenger_details

            text = text or ""
            parsed = parse_passenger_details(text, text) or {}

            name = (parsed.get("name") or "").strip()
            id_no = (parsed.get("id_no") or "").strip()
            nationality = (parsed.get("nationality") or "").strip()

            # naive confidence scoring
            confidence = 0
            if name:
                confidence += 40
            if id_no:
                confidence += 40
            if nationality:
                confidence += 20

            parsed["confidence"] = min(confidence, 100)

            return {
                "name": name,
                "id_no": id_no,
                "nationality": nationality,
                "confidence": parsed.get("confidence", 0),
            }
        except Exception as e:
            frappe.log_error(f"Parsing OCR text failed: {e}", "EnhancedTesseractOCR")
            return {
                "name": "",
                "id_no": "",
                "nationality": "",
                "confidence": 0,
            }

    # dummy methods to satisfy OCRManager.verify_and_learn()
    def learn_from_correction(self, original_text, corrected_text):
        try:
            if original_text and corrected_text and original_text != corrected_text:
                self.learning_data["corrections"][original_text] = corrected_text
        except Exception:
            pass

    def learn_from_verified_data(self, ocr_text, verified_data):
        # keep it no-op for now; you can implement later if needed
        return
