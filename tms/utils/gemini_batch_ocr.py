# tms/utils/gemini_batch_ocr.py

from __future__ import annotations
import os
import mimetypes
from typing import List, Dict, Any

from google import genai
from google.genai import types


DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# JSON schema to force structured output
PASSENGER_SCHEMA = {
    "type": "object",
    "properties": {
        "passengers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "full_name": {"type": "string"},
                    "id_no": {"type": "string"},
                    "nationality": {"type": "string"},
                    "confidence": {"type": "number"},
                    "notes": {"type": "string"},
                },
                "required": ["index", "full_name", "id_no", "nationality", "confidence", "notes"],
            },
        },
        "global_notes": {"type": "string"},
    },
    "required": ["passengers", "global_notes"],
}

def _guess_mime(path: str) -> str:
    mt, _ = mimetypes.guess_type(path)
    return mt or "application/octet-stream"

def gemini_extract_passengers_batch(
    file_paths: List[str],
    expected_count: int,
    model: str = DEFAULT_MODEL,
) -> Dict[str, Any]:
    """
    One Gemini call for multiple passenger ID images.
    Returns dict: {passengers: [...], global_notes: "..."}
    """

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY (or GOOGLE_API_KEY) environment variable")

    client = genai.Client(api_key=api_key)

    # Build prompt
    prompt = f"""
You will receive {len(file_paths)} passenger ID images (one person per image), in order.
Extract passenger information from EACH image and return ONLY valid JSON that matches the schema.

Rules:
- Keep passenger order same as images (first image = index 1, second = index 2, etc.)
- Do NOT merge two images into one passenger.
- If a field is not readable, return empty string "".
- Do NOT guess or invent ID numbers.
- confidence is 0.0 to 1.0 (how sure you are the extracted fields are correct).
- The output must contain exactly {expected_count} passengers in the passengers array.

Fields needed:
- full_name (English or Arabic as printed)
- id_no (Iqama/National ID/Passport number)
- nationality (as printed; if not available use "")

Return JSON only.
""".strip()

    # Add images as inline parts
    contents = [prompt]

    for p in file_paths:
        mime = _guess_mime(p)
        with open(p, "rb") as f:
            data = f.read()
        contents.append(
            types.Part.from_bytes(data=data, mime_type=mime)
        )

    # Force JSON output with schema
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=PASSENGER_SCHEMA,
        temperature=0.0,
    )

    resp = client.models.generate_content(
        model=model,
        contents=contents,
        config=config,
    )

    # google-genai returns JSON text in resp.text for JSON responses
    # If SDK changes, handle both.
    if getattr(resp, "parsed", None) is not None:
        return resp.parsed  # structured output parsing
    if getattr(resp, "text", None):
        import json
        return json.loads(resp.text)

    raise RuntimeError("Gemini returned empty response")
