# apps/tms/tms/utils/ocr_utils.py

import os
import frappe
import pytesseract
from PIL import Image
import arabic_reshaper
from bidi.algorithm import get_display


def _preprocess_image(image_path: str) -> Image.Image:
    """Simple preprocessing using only PIL (no OpenCV)."""
    img = Image.open(image_path)

    # convert to grayscale for more stable OCR
    try:
        img = img.convert("L")
    except Exception:
        pass

    return img


def _fix_arabic(text: str) -> str:
    """Reshape and reorder Arabic text for correct display."""
    try:
        reshaped = arabic_reshaper.reshape(text)
        return get_display(reshaped)
    except Exception:
        return text


def extract_text_from_file(file_url: str):
    """
    Extracts bilingual (Arabic + English) text from an image file_url.

    Supports:
      /files/xxx.jpg           (public)
      /private/files/xxx.jpg   (private)

    Returns: (raw_text, fixed_text)
    """
    if not file_url:
        return "", ""

    filename = os.path.basename(file_url)

    # decide public vs private from URL prefix
    if str(file_url).startswith("/private/"):
        file_path = frappe.get_site_path("private", "files", filename)
    else:
        file_path = frappe.get_site_path("public", "files", filename)

    if not os.path.exists(file_path):
        frappe.log_error(f"OCR file not found: {file_path}", "OCR Utils")
        return "", ""

    pil_img = _preprocess_image(file_path)

    config = "--oem 3 --psm 6 -c preserve_interword_spaces=1"
    raw_text = pytesseract.image_to_string(pil_img, lang="eng+ara", config=config)

    # Fallback: try original image if preprocessed is weak
    if not raw_text or len(raw_text.strip()) < 10:
        raw_text = pytesseract.image_to_string(
            Image.open(file_path),
            lang="eng+ara",
            config=config,
        )

    fixed_text = _fix_arabic(raw_text)

    frappe.logger().info(f"OCR RAW: {raw_text[:200]}")
    frappe.logger().info(f"OCR FIXED: {fixed_text[:200]}")

    return raw_text, fixed_text
