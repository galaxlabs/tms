import os, json, subprocess
import frappe

THRESHOLD = 0.80

def _call_gemini_batch(expected_count: int, file_paths: list[str]) -> dict:
    """
    Calls gemini runner (in gemini-venv) and returns parsed JSON dict.
    """
    venv_python = os.getenv("GEMINI_VENV_PYTHON", "/home/xg/gemini-venv/bin/python")
    runner = "/home/xg/xg-b/apps/tms/tms/scripts/gemini_batch_runner.py"

    cmd = [venv_python, runner, str(expected_count), *file_paths]
    r = subprocess.run(cmd, capture_output=True, text=True)

    if r.returncode != 0:
        raise RuntimeError(f"Gemini runner failed:\nSTDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}")

    return json.loads(r.stdout)

def _abs_path_from_file_url(site_name: str, file_url: str) -> str:
    # file_url like /private/files/abc.jpg or /files/abc.jpg
    return f"/home/xg/xg-b/sites/{site_name}{file_url}"

def process_passenger_images_for_trip(
    site_name: str,
    trip_name: str,
    file_urls_in_order: list[str],
    expected_count: int,
    source: str = "WhatsApp Message",
) -> dict:
    """
    - Calls Gemini once with all images
    - UPSERT OCR History rows (fingerprint unique is already enforced in OCR History)
    - Returns ok/resend_indexes/ocr_history_ids
    """
    from tms.scripts.process_passenger_images import upsert_ocr_history, confidence_gate

    file_paths = [_abs_path_from_file_url(site_name, u) for u in file_urls_in_order]
    result = _call_gemini_batch(expected_count, file_paths)

    ocr_ids = []
    for i, abs_path in enumerate(file_paths, start=1):
        passenger = result["passengers"][i-1]
        # save linked to Trip (your doctype has trip field)
        ocr_id = upsert_ocr_history(site_name, abs_path, passenger, source=source)
        # link trip (upsert_ocr_history currently doesn’t set trip; do it here)
        try:
            doc = frappe.get_doc("OCR History", ocr_id)
            doc.trip = trip_name
            doc.save(ignore_permissions=True)
        except Exception:
            pass
        ocr_ids.append(ocr_id)

    frappe.db.commit()

    bad = confidence_gate(result["passengers"])
    if bad:
        return {"ok": False, "resend_indexes": bad, "ocr_history_ids": ocr_ids}
    return {"ok": True, "ocr_history_ids": ocr_ids}
