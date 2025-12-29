import json
import hashlib
import frappe
from frappe.utils import now_datetime

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

def run():
    site_name = "tms-erp.online"

    file_paths = [
        "/home/xg/xg-b/sites/tms-erp.online/private/files/Iqama.jpeg",
        "/home/xg/xg-b/sites/tms-erp.online/private/files/WhatsApp Image 2025-10-13 at 8.20.57 AM32726a01f62e.jpeg",
        "/home/xg/xg-b/sites/tms-erp.online/private/files/WhatsApp Image 2025-09-29 at 01.51.13_4f977aba.jpg",
    ]

    gemini_result = {
      "passengers": [
        {"index": 1, "full_name": "MOHAMMAD SHOHEL DULAL MIAH", "id_no": "2443792532", "nationality": "Bangladesh", "confidence": 0.95, "notes": ""},
        {"index": 2, "full_name": "NAZIA MAJEED", "id_no": "R5283416", "nationality": "PAKISTANI", "confidence": 0.95, "notes": ""},
        {"index": 3, "full_name": "AHMED MAHMOUD RASHAD MAHMOUD", "id_no": "2574030033", "nationality": "Egypt", "confidence": 0.95, "notes": ""},
      ],
      "global_notes": ""
    }

    saved = []

    for i, abs_path in enumerate(file_paths, start=1):
        passenger = gemini_result["passengers"][i - 1]

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
        doc.source = "WhatsApp Message"
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

        saved.append(doc.name)

    frappe.db.commit()
    print("SAVED:", saved)

if __name__ == "__main__":
    run()
