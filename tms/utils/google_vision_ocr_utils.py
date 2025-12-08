# tms/utils/google_vision_ocr_utils.py

import io
from pathlib import Path

import frappe
from google.cloud import vision


def _get_gvision_client() -> vision.ImageAnnotatorClient:
    """
    Build a Google Vision client.

    You can configure either:
      - site_config.json: "google_vision_credentials": "/path/to/creds.json"
      - or env: GOOGLE_APPLICATION_CREDENTIALS

    If site_config key is set, we pass that explicitly.
    """
    creds_path = frappe.conf.get("google_vision_credentials")

    if creds_path:
        from google.oauth2 import service_account

        credentials = service_account.Credentials.from_service_account_file(creds_path)
        return vision.ImageAnnotatorClient(credentials=credentials)

    # Fallback: use env GOOGLE_APPLICATION_CREDENTIALS
    return vision.ImageAnnotatorClient()


def extract_text_google(image_path: str) -> str:
    """
    Extracts bilingual (Arabic + English) text from image using Google Vision.

    image_path = absolute path on disk (not File.file_url).
    """
    client = _get_gvision_client()

    path = Path(image_path)
    if not path.exists():
        frappe.throw(f"Google Vision: file not found: {image_path}")

    with path.open("rb") as f:
        content = f.read()

    image = vision.Image(content=content)

    # You can tune this later (DOCUMENT_TEXT_DETECTION vs TEXT_DETECTION)
    response = client.document_text_detection(image=image)

    if response.error.message:
        frappe.log_error(response.error.message, "Google Vision OCR Error")
        return ""

    # full text is in .full_text_annotation
    text = response.full_text_annotation.text or ""

    return text.strip()
