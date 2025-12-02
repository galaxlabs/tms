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
    Extracts bilingual (Arabic + English) text from an image.
    Returns both raw and fixed versions for use in the parser.
    """

    # file_url is like /private/files/xxx.jpg → we only need the basename
    file_path = frappe.get_site_path("private", "files", os.path.basename(file_url))

    # Preprocess the image for better accuracy (PIL only)
    pil_img = _preprocess_image(file_path)

    config = "--oem 3 --psm 6 -c preserve_interword_spaces=1"
    raw_text = pytesseract.image_to_string(pil_img, lang="eng+ara", config=config)

    # Fallback: try reading the original image if the preprocessed one fails
    if not raw_text or len(raw_text.strip()) < 10:
        raw_text = pytesseract.image_to_string(
            Image.open(file_path),
            lang="eng+ara",
            config=config,
        )

    # Fix Arabic right-to-left order
    fixed_text = _fix_arabic(raw_text)

    frappe.logger().info(f"OCR RAW: {raw_text[:200]}")
    frappe.logger().info(f"OCR FIXED: {fixed_text[:200]}")

    # ✅ Return both versions (tuple)
    return raw_text, fixed_text
