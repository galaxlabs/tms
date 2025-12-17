# tms/utils/gvision_docai.py

import io
import os
import frappe

from google.cloud import vision
from google.cloud import documentai_v1 as documentai
from google.api_core.client_options import ClientOptions


def _ensure_google_credentials():
    key_path = getattr(frappe.conf, "google_vision_key_path", None)
    if key_path and os.path.exists(key_path):
        os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", key_path)


def detect_text_gvision(file_path: str) -> str:
    """
    Simple text extraction using Google Cloud Vision (ImageAnnotatorClient).
    Works great for JPG, PNG, etc.
    """
    _ensure_google_credentials()

    client = vision.ImageAnnotatorClient()

    with open(file_path, "rb") as f:
        content = f.read()

    image = vision.Image(content=content)
    response = client.text_detection(image=image)

    if response.error.message:
        frappe.log_error(
            f"Google Vision error: {response.error.message}",
            "GoogleVision OCR",
        )
        return ""

    texts = response.text_annotations
    if not texts:
        return ""

    # texts[0].description = full detected text
    return texts[0].description or ""


def detect_text_docai(
    file_path: str,
    project_id: str,
    location: str,
    processor_id: str,
) -> str:
    """
    Text extraction using Google Document AI.

    You must set up a Processor in GCP and pass:
    - project_id
    - location (e.g. 'us' or 'eu')
    - processor_id (from DocAI console)
    """
    _ensure_google_credentials()

    client_options = ClientOptions(
        api_endpoint=f"{location}-documentai.googleapis.com"
    )
    client = documentai.DocumentProcessorServiceClient(
        client_options=client_options
    )

    name = client.processor_path(project_id, location, processor_id)

    with open(file_path, "rb") as f:
        image_content = f.read()

    # You can change mime_type to "image/jpeg" for images
    raw_document = documentai.RawDocument(
        content=image_content,
        mime_type="application/pdf",
    )

    request = documentai.ProcessRequest(
        name=name,
        raw_document=raw_document,
    )

    result = client.process_document(request=request)
    doc = result.document

    # doc.text is the full text content
    return doc.text or ""
