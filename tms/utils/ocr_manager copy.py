# /home/xg/xg-b/apps/tms/tms/utils/ocr_manager.py
# tms/utils/ocr_manager.py
import os
from pathlib import Path

import frappe


class OCRManager:
    def __init__(self):
        # Just keep a simple in-memory history for debugging/stats
        self.ocr_history = []

    # ------------------------------------------------------------------
    # Engine selection + file path
    # ------------------------------------------------------------------

    def _engine_from_conf(self) -> str:
        """
        Read frappe.conf.ocr_engine and normalise.
        Allowed values: gvision, tesseract, auto
        Default: gvision
        """
        value = (frappe.conf.get("ocr_engine") or "gvision").lower()
        if value not in {"gvision", "tesseract", "auto"}:
            value = "gvision"
        return value

    def get_file_path(self, file_url: str) -> str:
        """Convert /files/xxx.jpg or /private/files/xxx.jpg to full path."""
        if not file_url:
            return ""

        name = Path(file_url).name

        if file_url.startswith("/private/"):
            return frappe.get_site_path("private", "files", name)
        else:
            return frappe.get_site_path("public", "files", name)

    # ------------------------------------------------------------------
    # Engines
    # ------------------------------------------------------------------

    def _run_gvision(self, file_path: str) -> str:
        """OCR using Google Cloud Vision."""
        from google.cloud import vision
        from google.oauth2 import service_account

        key_path = frappe.conf.get("google_vision_key_path")
        if not key_path or not os.path.exists(key_path):
            raise RuntimeError(
                f"google_vision_key_path missing or not found: {key_path}"
            )

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

        # texts[0] is the full text block
        return texts[0].description or ""

    def _run_tesseract(self, file_path: str) -> str:
        """Simple local Tesseract using only PIL + pytesseract (no cv2)."""
        from PIL import Image
        import pytesseract

        img = Image.open(file_path)
        try:
            img = img.convert("L")  # grayscale
        except Exception:
            pass

        config = "--oem 3 --psm 6 -c preserve_interword_spaces=1"
        text = pytesseract.image_to_string(img, lang="eng+ara", config=config)
        return (text or "").strip()

    # ------------------------------------------------------------------
    # Main entry
    # ------------------------------------------------------------------

    def extract_from_image(self, file_url: str) -> dict:
        """
        Main OCR call.

        Returns:
        {
          "raw_text": "...",
          "structured_data": {
              "name": "...",
              "id_no": "...",
              "nationality": "...",
              "confidence": 0-100
          },
          "ocr_engine": "gvision" | "tesseract" | "none"
        }
        """
        from tms.utils.parser import parse_passenger_details

        file_path = self.get_file_path(file_url)

        if not file_path or not os.path.exists(file_path):
            frappe.log_error(f"OCR file not found: {file_path}", "OCRManager")
            return {
                "raw_text": "",
                "structured_data": {
                    "name": "",
                    "id_no": "",
                    "nationality": "",
                    "confidence": 0,
                },
                "ocr_engine": "none",
            }

        engine_pref = self._engine_from_conf()
        raw_text = ""
        engine_used = "none"

        # 1) Choose engine
        if engine_pref == "gvision":
            try:
                raw_text = self._run_gvision(file_path)
                engine_used = "gvision"
            except Exception as e:
                frappe.log_error(
                    "Google Vision OCR failed",
                    f"Google Vision OCR failed: {e}",
                )

        elif engine_pref == "tesseract":
            try:
                raw_text = self._run_tesseract(file_path)
                engine_used = "tesseract"
            except Exception as e:
                frappe.log_error(
                    "Tesseract OCR failed",
                    f"Tesseract OCR failed: {e}",
                )

        elif engine_pref == "auto":
            # Try Google Vision first
            try:
                raw_text = self._run_gvision(file_path)
                engine_used = "gvision"
            except Exception as e:
                frappe.log_error(
                    "Google Vision OCR failed (auto)",
                    f"Google Vision OCR failed (auto): {e}",
                )
                raw_text = ""

            # Fallback to Tesseract if Vision returns nothing / fails
            if not raw_text:
                try:
                    raw_text = self._run_tesseract(file_path)
                    engine_used = "tesseract"
                except Exception as e:
                    frappe.log_error(
                        "Tesseract OCR failed (auto)",
                        f"Tesseract OCR failed (auto): {e}",
                    )

        # 2) If still nothing, return empty structured block
        if not raw_text:
            structured = {
                "name": "",
                "id_no": "",
                "nationality": "",
                "confidence": 0,
            }
        else:
            # Parse to name / id / nationality
            try:
                parsed = parse_passenger_details(raw_text, raw_text) or {}
            except Exception as e:
                frappe.log_error(
                    "parse_passenger_details failed",
                    f"parse_passenger_details failed: {e}",
                )
                parsed = {}

            name = (parsed.get("name") or "").strip()
            id_no = (parsed.get("id_no") or "").strip()
            nationality = (parsed.get("nationality") or "").strip()

            confidence = 0
            if name:
                confidence += 40
            if id_no:
                confidence += 40
            if nationality:
                confidence += 20

            structured = {
                "name": name,
                "id_no": id_no,
                "nationality": nationality,
                "confidence": min(confidence, 100),
            }

        # History in memory (useful if you later add a UI or stats)
        self.ocr_history.append(
            {
                "file_url": file_url,
                "raw_text": raw_text,
                "extracted_data": structured,
                "engine": engine_used,
                "timestamp": frappe.utils.now(),
            }
        )

        return {
            "raw_text": raw_text,
            "structured_data": structured,
            "ocr_engine": engine_used,
        }


# ----------------------------------------------------------------------
# Helper used by WhatsApp bot / other code
# ----------------------------------------------------------------------


def analyze_id_document(file_url: str) -> dict:
    """
    Thin wrapper used by WhatsApp bot and other code.

    Returns a normalized dict:
      full_name, id_no, nationality, raw_text, fixed_text, confidence, engine, json_data
    """
    mgr = OCRManager()
    base = mgr.extract_from_image(file_url)

    raw_text = base.get("raw_text") or ""
    structured = base.get("structured_data") or {}

    return {
        "full_name": structured.get("name", "") or "",
        "id_no": structured.get("id_no", "") or "",
        "nationality": structured.get("nationality", "") or "",
        "raw_text": raw_text,
        "fixed_text": raw_text,  # if later you want to reshape Arabic, change here
        "confidence": structured.get("confidence", 0) or 0,
        "engine": base.get("ocr_engine") or "none",
        "json_data": structured,
    }



# import os
# import frappe
# from pathlib import Path


# class OCRManager:
#     def __init__(self):
#         self.ocr_history = []

#     def _engine_from_conf(self) -> str:
#         val = (frappe.conf.get("ocr_engine") or "openai").lower()
#         if val not in ("openai", "gvision", "auto"):
#             return "openai"
#         return val

#     def get_file_path(self, file_url: str) -> str:
#         name = Path(file_url).name
#         if file_url.startswith("/private/"):
#             return frappe.get_site_path("private", "files", name)
#         return frappe.get_site_path("public", "files", name)

#     def _run_openai(self, file_path: str) -> str:
#         from tms.utils.openai_ocr_utils import extract_text_openai
#         return extract_text_openai(file_path) or ""

#     # (you can add _run_gvision later)

#     def extract_from_image(self, file_url: str) -> dict:
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

#         # For now we only care about OpenAI path
#         # (gvision / auto will work later when you add Google's code)
#         if engine_pref in ("openai", "auto"):
#             try:
#                 raw_text = self._run_openai(file_path)
#                 engine_used = "openai"
#             except Exception as e:
#                 frappe.log_error("OpenAI OCR failed", f"OpenAI OCR failed: {e}")
#                 raw_text = ""
#                 engine_used = "openai"

#         # 2) parse
#         if raw_text:
#             try:
#                 parsed = parse_passenger_details(raw_text, raw_text) or {}
#             except Exception as e:
#                 frappe.log_error(f"parse_passenger_details failed: {e}", "OCRManager")
#                 parsed = {}
#         else:
#             parsed = {}

#         name = (parsed.get("name") or "").strip()
#         id_no = (parsed.get("id_no") or "").strip()
#         nationality = (parsed.get("nationality") or "").strip()

#         confidence = 0
#         if name:
#             confidence += 40
#         if id_no:
#             confidence += 40
#         if nationality:
#             confidence += 20

#         structured = {
#             "name": name,
#             "id_no": id_no,
#             "nationality": nationality,
#             "confidence": min(confidence, 100),
#         }

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


# def analyze_id_document(file_url: str) -> dict:
#     """
#     Normalized wrapper used by WhatsApp bot / Trip.
#     """
#     mgr = OCRManager()
#     result = mgr.extract_from_image(file_url)

#     raw_text = result.get("raw_text") or ""
#     structured = result.get("structured_data") or {}

#     return {
#         "full_name": structured.get("name", "") or "",
#         "id_no": structured.get("id_no", "") or "",
#         "nationality": structured.get("nationality", "") or "",
#         "raw_text": raw_text,
#         "fixed_text": raw_text,
#         "confidence": structured.get("confidence", 0) or 0,
#         "engine": result.get("ocr_engine") or "openai",
#         "json_data": structured,
#     }

# import os
# from pathlib import Path

# import frappe


# class OCRManager:
#     """
#     OCR manager that can use:
#       - OpenAI Vision
#       - Google Vision

#     Engine is chosen by:
#       frappe.conf["ocr_engine"] in site_config.json:
#         "openai"  -> OpenAI Vision
#         "gvision" -> Google Vision
#         "auto"    -> try Google Vision first, then OpenAI
#     """

#     def __init__(self):
#         self.ocr_history: list[dict] = []

#     # ------------------------------------------------------------------
#     # File path helper
#     # ------------------------------------------------------------------
#     def get_file_path(self, file_url: str) -> str:
#         """
#         Convert a File.file_url like:
#             /files/xxx.jpg
#             /private/files/xxx.jpg
#         to an absolute path on disk.
#         """
#         file_url = file_url or ""
#         name = Path(file_url).name
#         if not name:
#             return ""

#         if file_url.startswith("/private/"):
#             return frappe.get_site_path("private", "files", name)
#         else:
#             return frappe.get_site_path("public", "files", name)

#     # ------------------------------------------------------------------
#     # Engine selection helpers
#     # ------------------------------------------------------------------
#     def _engine_from_conf(self) -> str:
#         """
#         Read preferred OCR engine from site_config.json:
#           "ocr_engine": "openai" | "gvision" | "auto"
#         Default: "openai"
#         """
#         eng = (frappe.conf.get("ocr_engine") or "openai").lower()
#         if eng not in ("openai", "gvision", "auto"):
#             eng = "openai"
#         return eng

#     def _run_openai(self, file_path: str) -> str:
#         """Run OpenAI Vision and return raw text."""
#         from tms.utils.openai_ocr_utils import extract_text_openai

#         return extract_text_openai(file_path) or ""
    
#     def _run_gvision(self, file_path: str) -> str:
#         from tms.utils.google_vision_ocr_utils import extract_text_google

#         return extract_text_google(file_path) or ""

#     # ------------------------------------------------------------------
#     # Core OCR
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
#           "ocr_engine": "openai" | "gvision" | "none"
#         }
#         """
#         import os
#         from tms.utils.parser import parse_passenger_details

#         file_path = self.get_file_path(file_url)

#         # -----------------------------
#         # 0) Check file exists
#         # -----------------------------
#         if not file_path or not os.path.exists(file_path):
#             frappe.log_error(
#                 "OCR file not found",
#                 f"OCRManager.extract_from_image: file_path={file_path}, file_url={file_url}",
#             )
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

#         engine_pref = self._engine_from_conf()  # "openai" | "gvision" | "auto"
#         raw_text = ""
#         engine_used = "none"

#         # -----------------------------
#         # 1) Decide which engine to try
#         # -----------------------------
#         if engine_pref == "openai":
#             try:
#                 raw_text = self._run_openai(file_path)
#                 engine_used = "openai"
#             except Exception:
#                 # ✅ short title, full traceback in message → no length issue
#                 frappe.log_error(
#                     "OpenAI OCR failed",
#                     frappe.get_traceback(),
#                 )
#                 raw_text = ""
#                 engine_used = "openai"

#         elif engine_pref == "gvision":
#             try:
#                 raw_text = self._run_gvision(file_path)
#                 engine_used = "gvision"
#             except Exception:
#                 frappe.log_error(
#                     "Google Vision OCR failed",
#                     frappe.get_traceback(),
#                 )
#                 raw_text = ""
#                 engine_used = "gvision"

#         elif engine_pref == "auto":
#             # Try Google Vision first
#             try:
#                 raw_text = self._run_gvision(file_path)
#                 engine_used = "gvision"
#             except Exception:
#                 frappe.log_error(
#                     "Google Vision OCR failed (auto)",
#                     frappe.get_traceback(),
#                 )
#                 raw_text = ""

#             # If Vision failed or returned empty, fall back to OpenAI
#             if not raw_text:
#                 try:
#                     raw_text = self._run_openai(file_path)
#                     engine_used = "openai"
#                 except Exception:
#                     frappe.log_error(
#                         "OpenAI OCR failed (auto)",
#                         frappe.get_traceback(),
#                     )
#                     raw_text = ""
#                     engine_used = "openai"

#         # -----------------------------
#         # 2) Parse structured data
#         # -----------------------------
#         if raw_text:
#             try:
#                 parsed = parse_passenger_details(raw_text, raw_text) or {}
#             except Exception:
#                 frappe.log_error(
#                     "parse_passenger_details failed",
#                     frappe.get_traceback(),
#                 )
#                 parsed = {}
#         else:
#             parsed = {}

#         name = (parsed.get("name") or "").strip()
#         id_no = (parsed.get("id_no") or "").strip()
#         nationality = (parsed.get("nationality") or "").strip()

#         confidence = 0
#         if name:
#             confidence += 40
#         if id_no:
#             confidence += 40
#         if nationality:
#             confidence += 20

#         structured = {
#             "name": name,
#             "id_no": id_no,
#             "nationality": nationality,
#             "confidence": min(confidence, 100),
#         }

#         # -----------------------------
#         # 3) Store in in-memory history
#         # -----------------------------
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

#     # ------------------------------------------------------------------
#     # Optional stats API
#     # ------------------------------------------------------------------
#     def get_learning_stats(self) -> dict:
#         return {
#             "name_patterns": 0,
#             "id_patterns": 0,
#             "nationality_patterns": 0,
#             "corrections": 0,
#             "ocr_history_count": len(self.ocr_history),
#         }


# # ----------------------------------------------------------------------
# # MASTER API used by WhatsApp bot + Trip
# # ----------------------------------------------------------------------
# def analyze_id_document(file_url: str) -> dict:
#     """
#     Unified OCR API.

#     Returns:
#     {
#         "full_name": "...",
#         "id_no": "...",
#         "nationality": "...",
#         "raw_text": "...",
#         "fixed_text": "...",
#         "confidence": 0-100,
#         "engine": "openai" | "gvision" | "none",
#         "json_data": {...}
#     }
#     """
#     mgr = OCRManager()
#     base = mgr.extract_from_image(file_url)

#     raw_text = base.get("raw_text") or ""
#     structured = base.get("structured_data") or {}

#     return {
#         "full_name": structured.get("name", "") or "",
#         "id_no": structured.get("id_no", "") or "",
#         "nationality": structured.get("nationality", "") or "",
#         "raw_text": raw_text,
#         "fixed_text": raw_text,
#         "confidence": structured.get("confidence", 0) or 0,
#         "engine": base.get("ocr_engine", "none"),
#         "json_data": structured,
#     }

# # # tms/utils/ocr_manager.py

# # import os
# # import json
# # from pathlib import Path

# # import frappe


# # class OCRManager:
# #     """
# #     Single, clean OCR manager using EnhancedTesseractOCR.
# #     - Resolves File.file_url -> actual filesystem path (private/public)
# #     - Extracts raw text + structured fields
# #     - Keeps in-memory history for learning/stats
# #     """

# #     def __init__(self):
# #         self.tesseract_ocr = self.init_tesseract_ocr()
# #         self.ocr_history = []

# #     def init_tesseract_ocr(self):
# #         """Initialize Tesseract OCR with error handling"""
# #         try:
# #             from .enhanced_tesseract_ocr import EnhancedTesseractOCR
# #             return EnhancedTesseractOCR()
# #         except Exception as e:
# #             frappe.log_error(f"Initializing Tesseract OCR failed: {e}", "OCRManager")
# #             # hard fail so we notice during dev
# #             raise

# #     # ------------------------------------------------------------------
# #     # FILE PATH RESOLUTION (IMPORTANT PART)
# #     # ------------------------------------------------------------------
# #     def get_file_path(self, file_url: str) -> str:
# #         """
# #         Convert File.file_url to an actual filesystem path.

# #         Tries BOTH:
# #           - site/private/files/<basename>
# #           - site/public/files/<basename>

# #         and logs clearly if nothing found.
# #         """
# #         try:
# #             if not file_url:
# #                 return ""

# #             # normalise URL to just filename
# #             name = Path(str(file_url)).name

# #             private_path = frappe.get_site_path("private", "files", name)
# #             public_path = frappe.get_site_path("public", "files", name)

# #             if os.path.exists(private_path):
# #                 return private_path

# #             if os.path.exists(public_path):
# #                 return public_path

# #             # Nothing found → log with full info
# #             frappe.log_error(
# #                 f"OCR file not found.\n"
# #                 f"file_url        = {file_url}\n"
# #                 f"private_path    = {private_path}\n"
# #                 f"public_path     = {public_path}",
# #                 "OCRManager.get_file_path",
# #             )
# #             return ""
# #         except Exception as e:
# #             frappe.log_error(f"Getting file path failed for {file_url}: {e}", "OCRManager")
# #             return ""

# #     # ------------------------------------------------------------------
# #     # LOW-LEVEL OCR
# #     # ------------------------------------------------------------------
# #     def extract_from_image(self, file_url: str, use_learning: bool = True) -> dict:
# #         """
# #         Low-level OCR call used by master API and WhatsApp bot.

# #         Returns:
# #         {
# #             "raw_text": "...",
# #             "structured_data": {
# #                 "name": "...",
# #                 "id_no": "...",
# #                 "nationality": "...",
# #                 "confidence": 0-100,
# #             },
# #             "ocr_engine": "tesseract",
# #         }
# #         """
# #         try:
# #             file_path = self.get_file_path(file_url)

# #             if not file_path or not os.path.exists(file_path):
# #                 # Path not found → return empty skeleton
# #                 return {
# #                     "raw_text": "",
# #                     "structured_data": {
# #                         "name": "",
# #                         "id_no": "",
# #                         "nationality": "",
# #                         "confidence": 0,
# #                     },
# #                     "ocr_engine": "tesseract",
# #                 }

# #             # 1) Extract text using EnhancedTesseractOCR
# #             raw_text = self.tesseract_ocr.extract_text_with_tesseract(file_path) or ""

# #             # 2) Extract structured data from that text
# #             structured_data = self.tesseract_ocr.extract_structured_data(raw_text) or {}
# #             structured_data.setdefault("name", "")
# #             structured_data.setdefault("id_no", "")
# #             structured_data.setdefault("nationality", "")
# #             structured_data.setdefault("confidence", 0)

# #             # 3) Save in memory history (optional, for learning / stats)
# #             if use_learning:
# #                 self.ocr_history.append(
# #                     {
# #                         "file_url": file_url,
# #                         "file_path": file_path,
# #                         "raw_text": raw_text,
# #                         "extracted_data": structured_data,
# #                         "timestamp": frappe.utils.now(),
# #                     }
# #                 )

# #             return {
# #                 "raw_text": raw_text,
# #                 "structured_data": structured_data,
# #                 "ocr_engine": "tesseract",
# #             }
# #         except Exception as e:
# #             frappe.log_error(f"OCR extraction from image failed: {e}", "OCRManager")
# #             return {
# #                 "raw_text": "",
# #                 "structured_data": {
# #                     "name": "",
# #                     "id_no": "",
# #                     "nationality": "",
# #                     "confidence": 0,
# #                 },
# #                 "ocr_engine": "tesseract",
# #             }

# #     # ------------------------------------------------------------------
# #     # OPTIONAL: learning API (same idea as your old code)
# #     # ------------------------------------------------------------------
# #     def verify_and_learn(self, ocr_result_id, verified_data):
# #         """Verify OCR result and learn from corrections (optional)."""
# #         try:
# #             ocr_entry = None
# #             for entry in self.ocr_history:
# #                 if entry.get("id") == ocr_result_id:
# #                     ocr_entry = entry
# #                     break

# #             if ocr_entry and verified_data:
# #                 self.tesseract_ocr.learn_from_verified_data(
# #                     ocr_entry["raw_text"], verified_data
# #                 )

# #                 extracted = ocr_entry["extracted_data"]
# #                 if extracted.get("name") != verified_data.get("name"):
# #                     self.tesseract_ocr.learn_from_correction(
# #                         extracted.get("name", ""), verified_data.get("name", "")
# #                     )
# #         except Exception as e:
# #             frappe.log_error(f"Verifying and learning from OCR failed: {e}", "OCRManager")

# #     def batch_process(self, file_urls):
# #         """Process multiple files at once (Trip batch OCR, etc.)."""
# #         results = []
# #         for file_url in file_urls:
# #             try:
# #                 result = self.extract_from_image(file_url)
# #                 results.append(
# #                     {
# #                         "file_url": file_url,
# #                         "success": True,
# #                         "data": result,
# #                     }
# #                 )
# #             except Exception as e:
# #                 results.append(
# #                     {
# #                         "file_url": file_url,
# #                         "success": False,
# #                         "error": str(e),
# #                     }
# #                 )
# #         return results

# #     def get_learning_stats(self):
# #         """Get learning statistics."""
# #         try:
# #             ld = self.tesseract_ocr.learning_data
# #             return {
# #                 "name_patterns": len(ld.get("name_patterns", [])),
# #                 "id_patterns": len(ld.get("id_patterns", [])),
# #                 "nationality_patterns": len(ld.get("nationality_patterns", [])),
# #                 "corrections": len(ld.get("corrections", {})),
# #                 "ocr_history_count": len(self.ocr_history),
# #             }
# #         except Exception as e:
# #             frappe.log_error(f"Getting learning stats failed: {e}", "OCRManager")
# #             return {
# #                 "name_patterns": 0,
# #                 "id_patterns": 0,
# #                 "nationality_patterns": 0,
# #                 "corrections": 0,
# #                 "ocr_history_count": 0,
# #             }


# # # ---------------------------------------------------------------------------
# # # MASTER API: analyze_id_document (what WhatsApp bot & Trip call)
# # # ---------------------------------------------------------------------------


# # def analyze_id_document(file_url: str) -> dict:
# #     """
# #     Thin wrapper used by WhatsApp bot, Trip, etc.

# #     Uses OCRManager.extract_from_image() and normalizes to:
# #     {
# #         "full_name": "...",
# #         "id_no": "...",
# #         "nationality": "...",
# #         "raw_text": "...",
# #         "fixed_text": "...",
# #         "confidence": 0-100,
# #         "json_data": {...}
# #     }
# #     """
# #     mgr = OCRManager()
# #     result = mgr.extract_from_image(file_url)

# #     raw_text = result.get("raw_text") or ""
# #     structured = result.get("structured_data") or {}

# #     full_name = (structured.get("name") or "").strip()
# #     id_no = (structured.get("id_no") or "").strip()
# #     nationality = (structured.get("nationality") or "").strip()
# #     confidence = int(structured.get("confidence") or 0)

# #     return {
# #         "full_name": full_name,
# #         "id_no": id_no,
# #         "nationality": nationality,
# #         "raw_text": raw_text,
# #         # we can later add proper Arabic reshaping → for now same as raw_text
# #         "fixed_text": raw_text,
# #         "confidence": confidence,
# #         "json_data": structured,
# #     }
