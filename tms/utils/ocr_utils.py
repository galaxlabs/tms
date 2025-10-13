import os
import frappe
import pytesseract
from PIL import Image
import cv2
import numpy as np
import arabic_reshaper
from bidi.algorithm import get_display


def _preprocess_cv(image_path: str) -> Image.Image:
    """Preprocess the image to improve OCR accuracy (grayscale, threshold, etc.)."""
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(image_path)

    # Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Denoise and threshold
    gray = cv2.bilateralFilter(gray, 9, 75, 75)
    thr = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 31, 15
    )

    # Light dilation to connect broken Arabic characters
    kernel = np.ones((1, 1), np.uint8)
    thr = cv2.dilate(thr, kernel, iterations=1)

    return Image.fromarray(thr)


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

    file_path = frappe.get_site_path("private", "files", os.path.basename(file_url))

    # Preprocess the image for better accuracy
    pil_img = _preprocess_cv(file_path)

    config = "--oem 3 --psm 6 -c preserve_interword_spaces=1"
    raw_text = pytesseract.image_to_string(pil_img, lang="eng+ara", config=config)

    # Fallback: try reading the original image if the preprocessed one fails
    if not raw_text or len(raw_text.strip()) < 10:
        raw_text = pytesseract.image_to_string(Image.open(file_path), lang="eng+ara", config=config)

    # Fix Arabic right-to-left order
    fixed_text = _fix_arabic(raw_text)

    frappe.logger().info(f"OCR RAW: {raw_text[:200]}")
    frappe.logger().info(f"OCR FIXED: {fixed_text[:200]}")

    # ✅ Return both versions (tuple)
    return raw_text, fixed_text
