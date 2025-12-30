# tms/utils/passenger_ocr_service.py
import frappe
import json
from tms.utils.file_resolver import file_url_to_path
from tms.utils.gemini_batch_ocr import gemini_extract_passengers_batch
from tms.utils.bot_settings import get_settings

def _norm_conf(conf) -> float:
    try:
        c = float(conf or 0)
    except Exception:
        return 0.0
    if c > 1.0:
        c = c / 100.0
    if c < 0:
        c = 0.0
    if c > 1:
        c = 1.0
    return c

def _is_passenger_ok(p: dict, threshold: float) -> tuple[bool, float]:
    full_name = (p.get("full_name") or "").strip()
    id_no = (p.get("id_no") or "").strip()
    conf = _norm_conf(p.get("confidence"))
    # Hard validation
    if not full_name or len(full_name) < 3:
        return False, conf
    if not id_no or len(id_no) < 5:
        return False, conf
    if threshold and conf < threshold:
        return False, conf
    return True, conf

def process_passenger_images_batch(
    trip_name: str,
    file_urls: list[str],
    waba_message: str | None = None,
    reference_doctype: str = "WhatsApp Message",
) -> dict:
    """
    One Gemini call for all images.
    Creates OCR History rows for each document.
    Returns:
      {"ok": bool, "resend_indexes": [1-based], "ocr_history_ids": []}
    """
    settings, _ = get_settings()
    threshold = float(settings.confidence_threshold or 0)  # e.g. 0.7
    max_p = int(settings.max_passengers or 0)

    if max_p and len(file_urls) > max_p:
        file_urls = file_urls[:max_p]

    # Resolve paths
    paths = []
    bad = []
    for i, u in enumerate(file_urls, start=1):
        p = file_url_to_path(u)
        if not p:
            bad.append(i)
            paths.append(None)
        else:
            paths.append(p)

    # If any file path missing -> ask resend those
    if bad:
        return {"ok": False, "resend_indexes": bad, "ocr_history_ids": []}

    # Gemini batch
    out = gemini_extract_passengers_batch(paths)
    passengers = out.get("passengers") or []

    # Must match length exactly
    if len(passengers) != len(file_urls):
        # Force resend all (model didn’t follow instruction)
        return {"ok": False, "resend_indexes": list(range(1, len(file_urls) + 1)), "ocr_history_ids": []}

    ocr_ids = []
    resend = []

    for idx, (file_url, p) in enumerate(zip(file_urls, passengers), start=1):
        full_name = (p.get("full_name") or "").strip()
        id_no = (p.get("id_no") or "").strip()
        nationality = (p.get("nationality") or "").strip()
        raw_text = (p.get("raw_text") or "").strip()
        conf = _norm_conf(p.get("confidence"))

        ok, conf2 = _is_passenger_ok(p, threshold)
        if not ok:
            resend.append(idx)

        # Create OCR History row (dataset + reference)
        ocr = frappe.new_doc("OCR History")
        ocr.source = "WhatsApp Message"
        ocr.ocr_engine = "Gemini"
        ocr.confidence = conf2
        ocr.trip = trip_name
        ocr.waba_message = waba_message
        ocr.reference_doctype = reference_doctype
        ocr.reference_name = waba_message or ""
        # store file link if File exists
        file_doc_name = frappe.db.get_value("File", {"file_url": file_url}, "name")
        if file_doc_name:
            ocr.file = file_doc_name

        ocr.raw_text = raw_text
        ocr.full_name = full_name
        ocr.id_no = id_no
        ocr.nationality = nationality
        ocr.json_data = json.dumps(p, ensure_ascii=False)

        # NOTE: file_fingerprint: you said A1 is done. If you compute it elsewhere,
        # set it here. If not, we can add it here using your sha256 helper.
        ocr.insert(ignore_permissions=True)
        ocr_ids.append(ocr.name)

    return {"ok": (len(resend) == 0), "resend_indexes": resend, "ocr_history_ids": ocr_ids}

# import os, json, subprocess
# import frappe

# THRESHOLD = 0.80

# def _call_gemini_batch(expected_count: int, file_paths: list[str]) -> dict:
#     """
#     Calls gemini runner (in gemini-venv) and returns parsed JSON dict.
#     """
#     venv_python = os.getenv("GEMINI_VENV_PYTHON", "/home/xg/gemini-venv/bin/python")
#     runner = "/home/xg/xg-b/apps/tms/tms/scripts/gemini_batch_runner.py"

#     cmd = [venv_python, runner, str(expected_count), *file_paths]
#     r = subprocess.run(cmd, capture_output=True, text=True)

#     if r.returncode != 0:
#         raise RuntimeError(f"Gemini runner failed:\nSTDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}")

#     return json.loads(r.stdout)

# def _abs_path_from_file_url(site_name: str, file_url: str) -> str:
#     # file_url like /private/files/abc.jpg or /files/abc.jpg
#     return f"/home/xg/xg-b/sites/{site_name}{file_url}"

# def process_passenger_images_for_trip(
#     site_name: str,
#     trip_name: str,
#     file_urls_in_order: list[str],
#     expected_count: int,
#     source: str = "WhatsApp Message",
# ) -> dict:
#     """
#     - Calls Gemini once with all images
#     - UPSERT OCR History rows (fingerprint unique is already enforced in OCR History)
#     - Returns ok/resend_indexes/ocr_history_ids
#     """
#     from tms.scripts.process_passenger_images import upsert_ocr_history, confidence_gate

#     file_paths = [_abs_path_from_file_url(site_name, u) for u in file_urls_in_order]
#     result = _call_gemini_batch(expected_count, file_paths)

#     ocr_ids = []
#     for i, abs_path in enumerate(file_paths, start=1):
#         passenger = result["passengers"][i-1]
#         # save linked to Trip (your doctype has trip field)
#         ocr_id = upsert_ocr_history(site_name, abs_path, passenger, source=source)
#         # link trip (upsert_ocr_history currently doesn’t set trip; do it here)
#         try:
#             doc = frappe.get_doc("OCR History", ocr_id)
#             doc.trip = trip_name
#             doc.save(ignore_permissions=True)
#         except Exception:
#             pass
#         ocr_ids.append(ocr_id)

#     frappe.db.commit()

#     bad = confidence_gate(result["passengers"])
#     if bad:
#         return {"ok": False, "resend_indexes": bad, "ocr_history_ids": ocr_ids}
#     return {"ok": True, "ocr_history_ids": ocr_ids}
