# /home/xg/xg-b/apps/tms/tms/utils/openai_ocr_utils.py
import base64
from pathlib import Path
from typing import Union, List, Dict

import frappe
from openai import OpenAI


def _get_openai_client() -> OpenAI:
    """
    Create OpenAI client using site_config keys.
    """
    # Try both keys for safety
    api_key = (
        getattr(frappe.conf, "openai_api_key", None)
        or frappe.get_conf().get("OPENAI_API_KEY")
    )
    if not api_key:
        frappe.throw("OpenAI API key (openai_api_key or OPENAI_API_KEY) is not set")

    return OpenAI(api_key=api_key)


def extract_text_openai(image_path: str) -> str:
    """
    Extracts Arabic + English text from an image using a vision-capable model.
    Returns plain text.
    """
    client = _get_openai_client()

    image_file = Path(image_path)
    img_b64 = base64.b64encode(image_file.read_bytes()).decode("utf-8")

    # Data URI so the API doesn't need to fetch from your server
    image_url = f"data:image/jpeg;base64,{img_b64}"

    completion = client.chat.completions.create(
        # ✅ Use a model that definitely supports vision
        model="gpt-4.1-mini",   # you can switch to "gpt-4o" if you want
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an OCR engine. You CAN see images and must read ALL visible "
                    "Arabic and English text from ID/Passport/Iqama documents exactly as printed."
                ),
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Read every word and number on this document image. "
                            "Return all text as a single plain UTF-8 string."
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image_url,
                            # optional but helps in some cases:
                            "detail": "high",
                        },
                    },
                ],
            },
        ],
        temperature=0,
    )

    content = completion.choices[0].message.content

    # New SDK may return a string or list of blocks
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        text_parts = []
        for block in content:
            # {"type": "text", "text": "..."}
            if isinstance(block, dict) and block.get("type") == "text":
                text_parts.append(block.get("text", ""))
        return "\n".join(text_parts).strip()

    # Fallback
    return str(content or "").strip()
