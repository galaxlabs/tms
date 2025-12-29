import os, json, hashlib, subprocess
import frappe
from frappe.utils import now_datetime

THRESHOLD = 0.80

def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()

def path_to_file_url(site_name: str, abs_path: str) -> str:
    marker = f"/sites/{site_name}"
    if marker not in abs_path:
        raise ValueError(f"Path not inside site folder: {abs_path}")
    return abs_path.split(marker, 1)[1]

def call_gemini_batch(expected_count: int, file_paths: list[str]) -> dict:
    """
    Calls gemini-venv runner script and returns JSON dict.
    """
    venv_python = os.getenv("GEMINI_VENV_PYTHON", "/home/xg/gemini-venv/bin/python")
    runner = "/home/xg/xg-b/apps/tms/tms/scripts/gemini_batch_runner.py"

    cmd = [venv_python, runner, str(expected_count), *file_paths]
    r = subprocess.run(cmd, capture_output=True, text=True)

    if r.returncode != 0:
        raise RuntimeError(f"Gemini runner failed:\nSTDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}")

    return json.loads(r.stdout)

def upsert_ocr_history(site_name: str, abs_path: str, passenger: dict, source="WhatsApp Message") -> str:
    fp = sha256_file(abs_path)
    file_url = path_to_file_url(site_name, abs_path)
    file_name = frappe.db.get_value("File", {"file_url": file_url}, "name")

    existing = frappe.db.get_value("OCR History", {"file_fingerprint": fp}, "name")

    if existing:
        doc = frappe.get_doc("OCR History", existing)
    else:
        doc = frappe.get_doc({"doctype": "OCR History"})
        doc.file_fingerprint = fp

    doc.processed_on = now_datetime()
    doc.source = source
    doc.ocr_engine = "Gemini"
    doc.confidence = float(passenger.get("confidence") or 0)
    doc.file = file_name
    doc.full_name = passenger.get("full_name") or ""
    doc.id_no = passenger.get("id_no") or ""
    doc.nationality = passenger.get("nationality") or ""
    doc.json_data = json.dumps(passenger, ensure_ascii=False)

    if existing:
        doc.save(ignore_permissions=True)
    else:
        doc.insert(ignore_permissions=True)

    return doc.name

def confidence_gate(passengers: list[dict]) -> list[int]:
    bad = []
    for p in passengers:
        idx = int(p.get("index") or 0)
        conf = float(p.get("confidence") or 0)
        name_ok = bool((p.get("full_name") or "").strip())
        id_ok = bool((p.get("id_no") or "").strip())
        if not (conf >= THRESHOLD and name_ok and id_ok):
            bad.append(idx)
    return bad

def run():
    site_name = "tms-erp.online"

    file_paths = [
        "/home/xg/xg-b/sites/tms-erp.online/private/files/Iqama.jpeg",
        "/home/xg/xg-b/sites/tms-erp.online/private/files/WhatsApp Image 2025-10-13 at 8.20.57 AM32726a01f62e.jpeg",
        "/home/xg/xg-b/sites/tms-erp.online/private/files/WhatsApp Image 2025-09-29 at 01.51.13_4f977aba.jpg",
    ]
    expected_count = 3

    result = call_gemini_batch(expected_count, file_paths)

    # save / upsert
    ocr_ids = []
    for i, abs_path in enumerate(file_paths, start=1):
        passenger = result["passengers"][i-1]
        ocr_ids.append(upsert_ocr_history(site_name, abs_path, passenger))

    frappe.db.commit()

    # gate
    bad = confidence_gate(result["passengers"])

    if bad:
        print({"ok": False, "resend_indexes": bad, "ocr_history_ids": ocr_ids})
    else:
        print({"ok": True, "ocr_history_ids": ocr_ids})

if __name__ == "__main__":
    run()
