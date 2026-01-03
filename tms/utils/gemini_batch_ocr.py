# /home/xg/xg-b/apps/tms/tms/utils/gemini_batch_ocr.py
from __future__ import annotations

import json
import mimetypes
import os
import re
import time
import traceback
from typing import Any

import frappe
from google import genai
from google.genai import types

from tms.utils.bot_settings import get_settings


PASSENGER_SCHEMA = {
    "type": "object",
    "properties": {
        "passengers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "full_name": {"type": "string"},
                    "id_no": {"type": "string"},
                    "nationality": {"type": "string"},
                    "raw_text": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["full_name", "id_no", "nationality", "confidence"],
            },
        }
    },
    "required": ["passengers"],
}


def _guess_mime(path: str) -> str:
    mt, _ = mimetypes.guess_type(path)
    return mt or "application/octet-stream"


def _get_api_key() -> str:
    # Prefer site_config.json
    key = (frappe.conf.get("gemini_api_key") or "").strip()
    if key:
        return key

    # Optional: from doctype password field
    try:
        s, _ = get_settings()
        k2 = (s.get_password("gemini_api_key") or "").strip()
        if k2:
            return k2
    except Exception:
        pass

    return (os.environ.get("GEMINI_API_KEY") or "").strip()


def _get_client_and_model():
    s, _ = get_settings()
    model = (getattr(s, "gemini_model", "") or "gemini-2.5-flash").strip()

    key = _get_api_key()
    if not key:
        raise ValueError("gemini_api_key is not set (site_config or settings).")

    # IMPORTANT: google-genai HttpOptions.timeout is in MILLISECONDS
    # 180000ms = 180s
    timeout_ms = int(getattr(s, "gemini_timeout_ms", 0) or 180000)

    http_options = types.HttpOptions(timeout=timeout_ms)
    client = genai.Client(api_key=key, http_options=http_options)
    return client, model, timeout_ms


def _extract_json_block(text: str) -> str | None:
    if not text:
        return None
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s*```$", "", t)
    start = t.find("{")
    end = t.rfind("}")
    if start != -1 and end != -1 and end > start:
        return t[start : end + 1]
    return None


def _safe_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    return str(v).strip()


def _norm_conf(v: Any) -> float:
    try:
        c = float(v or 0)
    except Exception:
        c = 0.0
    if c > 1.0:
        c = c / 100.0
    return max(0.0, min(1.0, c))


def _clean_passenger_item(p: Any) -> dict:
    if not isinstance(p, dict):
        p = {}

    full_name = _safe_str(p.get("full_name"))
    id_no = _safe_str(p.get("id_no"))
    nationality = _safe_str(p.get("nationality"))

    raw_text = _safe_str(p.get("raw_text"))
    if raw_text:
        raw_text = raw_text.replace('"', "'")
        if len(raw_text) > 600:
            raw_text = raw_text[:600]

    confidence = _norm_conf(p.get("confidence"))
    # If model returned empty, keep a low confidence instead of 0
    if not (full_name or id_no or nationality) and confidence == 0.0:
        confidence = 0.1

    return {
        "full_name": full_name,
        "id_no": id_no,
        "nationality": nationality,
        "raw_text": raw_text,
        "confidence": confidence,
    }


def _resp_text_fallback(resp) -> str:
    t = (getattr(resp, "text", None) or "").strip()
    if t:
        return t

    cands = getattr(resp, "candidates", None) or []
    for c in cands:
        content = getattr(c, "content", None)
        parts = getattr(content, "parts", None) or []
        for part in parts:
            pt = (getattr(part, "text", None) or "").strip()
            if pt:
                return pt

    return ""


def _generate_with_retries(client, model: str, parts, config, tries: int = 3):
    last_err = None
    for attempt in range(1, tries + 1):
        try:
            return client.models.generate_content(model=model, contents=parts, config=config)
        except Exception as e:
            last_err = e
            # small backoff
            time.sleep(1.5 * attempt)

    raise last_err


def gemini_extract_passengers_batch(file_paths: list[str]) -> dict:
    """
    Always returns:
      {
        "passengers": [dict, ...]  # length == len(file_paths)
        "error": optional,
        "raw": optional,
        "timeout_ms": optional,
      }
    """
    file_paths = [p for p in (file_paths or []) if p]
    n = len(file_paths)

    raw_text = ""
    client = None
    timeout_ms = None

    try:
        client, model, timeout_ms = _get_client_and_model()

        prompt = """
You are an OCR + information extractor for passenger identity documents.
I will provide multiple documents (images or PDFs). The order matters.

Return ONLY valid JSON:
{
  "passengers": [
    {
      "full_name": "string",
      "id_no": "string",
      "nationality": "string",
      "raw_text": "string",
      "confidence": 0.0
    }
  ]
}

Rules (VERY IMPORTANT):
- passengers length MUST equal number of files (same order).
- confidence must be 0.0-1.0.
- raw_text MUST be max 600 characters. If longer, truncate.
- raw_text MUST NOT contain double quotes (") — replace them with single quotes (').
- If unreadable, return empty strings and confidence 0.1 (still include the item).
""".strip()

        parts: list[Any] = [types.Part.from_text(text=prompt)]

        for p in file_paths:
            with open(p, "rb") as f:
                parts.append(types.Part.from_bytes(data=f.read(), mime_type=_guess_mime(p)))

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=PASSENGER_SCHEMA,
            temperature=0.0,
            max_output_tokens=4096,
        )

        resp = _generate_with_retries(client, model, parts, config, tries=3)

        data = getattr(resp, "parsed", None)
        raw_text = _resp_text_fallback(resp)

        if not isinstance(data, dict):
            j = _extract_json_block(raw_text)
            if not j:
                frappe.log_error("GEMINI_BATCH_OCR_NO_JSON", raw_text[:2000] or "(empty raw_text)")
                return {"passengers": ([{}] * n), "error": "no_json_found", "raw": raw_text, "timeout_ms": timeout_ms}

            try:
                data = json.loads(j)
            except Exception as je:
                frappe.log_error(
                    "GEMINI_BATCH_OCR_JSON_DECODE_FAIL",
                    f"{je}\n\nRAW_HEAD:\n{(raw_text[:2000] or '(empty raw_text)')}",
                )
                return {"passengers": ([{}] * n), "error": f"json_decode_failed: {je}", "raw": raw_text, "timeout_ms": timeout_ms}

        passengers = data.get("passengers") if isinstance(data, dict) else []
        if not isinstance(passengers, list):
            passengers = []

        if len(passengers) < n:
            passengers = passengers + ([{}] * (n - len(passengers)))
        if len(passengers) > n:
            passengers = passengers[:n]

        passengers = [_clean_passenger_item(p) for p in passengers]
        return {"passengers": passengers, "raw": raw_text, "timeout_ms": timeout_ms}

    except Exception as e:
        frappe.log_error(
            title="GEMINI_BATCH_OCR_FAIL",
            message=f"{e}\n\ntimeout_ms={timeout_ms}\n\nRAW_HEAD:\n{(raw_text[:2000] or '(empty raw_text)')}\n\n{traceback.format_exc()}",
        )
        return {"passengers": ([{}] * n), "error": str(e), "raw": raw_text, "timeout_ms": timeout_ms}

    finally:
        try:
            if client:
                client.close()
        except Exception:
            pass
