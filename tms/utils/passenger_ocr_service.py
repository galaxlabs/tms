import frappe
import json
from tms.utils.file_resolver import file_url_to_path
from tms.utils.gemini_batch_ocr import gemini_extract_passengers_batch
from tms.utils.bot_settings import get_settings


def _normalize_passenger(p: dict) -> dict:
    p = p or {}

    def pick(*keys) -> str:
        for k in keys:
            v = p.get(k)
            if v is None:
                continue
            v = v.strip() if isinstance(v, str) else str(v).strip()
            if v:
                return v
        return ""

    return {
        "full_name": pick("full_name", "name", "passenger_name", "holder_name"),
        "id_no": pick(
            "id_no", "id_number", "passport_no", "passport_number",
            "iqama_no", "document_number", "idpassport_no"
        ),
        "nationality": pick("nationality", "nation"),
        "raw_text": (p.get("raw_text") or "").strip(),
        "confidence": p.get("confidence", None),
        "_raw": p,
    }


def _norm_conf(conf) -> float:
    try:
        c = float(conf or 0)
    except Exception:
        return 0.0
    if c > 1.0:
        c = c / 100.0
    return max(0.0, min(1.0, c))


def _is_passenger_ok(p: dict, threshold: float) -> tuple[bool, float]:
    full_name = (p.get("full_name") or "").strip()
    id_no = (p.get("id_no") or "").strip()

    conf_raw = p.get("confidence", None)
    conf = 1.0 if conf_raw is None else _norm_conf(conf_raw)

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
    settings, _ = get_settings()

    threshold = float(getattr(settings, "confidence_threshold", 0) or 0)
    if not int(getattr(settings, "resend_on_low_confidence", 1) or 0):
        threshold = 0.0

    max_p = int(getattr(settings, "max_passengers", 0) or 0)
    if max_p and len(file_urls) > max_p:
        file_urls = file_urls[:max_p]

    # Resolve paths (KEEP SAME LENGTH as file_urls)
    paths: list[str | None] = []
    bad: list[int] = []
    for i, u in enumerate(file_urls, start=1):
        p = file_url_to_path(u)
        if not p:
            bad.append(i)
        paths.append(p)

    if bad:
        return {"ok": False, "resend_indexes": bad, "ocr_history_ids": []}

    # Now safe to cast (no None exists)
    safe_paths: list[str] = [p for p in paths if p]

    frappe.log_error("WA OCR INPUT", f"trip={trip_name} urls={len(file_urls)} paths={len(safe_paths)}")

    out = gemini_extract_passengers_batch(safe_paths)

    # If Gemini errored: return error (and let bot show "OCR timeout, retry")
    if out.get("error"):
        return {
            "ok": False,
            "resend_indexes": list(range(1, len(file_urls) + 1)),
            "ocr_history_ids": [],
            "error": out.get("error"),
            "raw": out.get("raw"),
        }

    raw_passengers = out.get("passengers") or []
    passengers = [_normalize_passenger(x) for x in raw_passengers]

    # Enforce exact length (defensive)
    if len(passengers) < len(file_urls):
        passengers = passengers + ([_normalize_passenger({})] * (len(file_urls) - len(passengers)))
    if len(passengers) > len(file_urls):
        passengers = passengers[:len(file_urls)]

    frappe.log_error(
        "WA OCR OUTPUT_META",
        f"passengers_len={len(passengers)} keys0={(list(passengers[0].keys()) if passengers else None)}",
    )

    ocr_ids: list[str] = []
    resend: list[int] = []

    trip_exists = bool(trip_name and frappe.db.exists("Trip", trip_name))
    msg_exists = bool(waba_message and frappe.db.exists(reference_doctype, waba_message))

    for idx, (file_url, p) in enumerate(zip(file_urls, passengers), start=1):
        ok, conf2 = _is_passenger_ok(p, threshold)
        if not ok:
            resend.append(idx)

        full_name = p["full_name"]
        id_no = p["id_no"]
        nationality = p["nationality"]
        raw_text = p.get("raw_text") or ""

        frappe.log_error(
            "WA OCR ITEM",
            f"idx={idx} name={full_name!r} id={id_no!r} nat={nationality!r} conf={conf2!r}",
        )

        ocr = frappe.new_doc("OCR History")
        ocr.source = "WhatsApp Message"
        ocr.ocr_engine = "Gemini"
        ocr.confidence = conf2

        # Only set links if they exist
        if trip_exists:
            ocr.trip = trip_name

        if msg_exists:
            ocr.waba_message = waba_message
            ocr.reference_doctype = reference_doctype
            ocr.reference_name = waba_message

        file_doc_name = frappe.db.get_value("File", {"file_url": file_url}, "name")
        if file_doc_name:
            ocr.file = file_doc_name

        ocr.full_name = full_name
        ocr.id_no = id_no
        ocr.nationality = nationality
        if hasattr(ocr, "raw_text"):
            ocr.raw_text = raw_text

        ocr.json_data = json.dumps(p.get("_raw") or {}, ensure_ascii=False)

        ocr.insert(ignore_permissions=True)
        ocr_ids.append(ocr.name)

    return {
        "ok": (len(resend) == 0),
        "resend_indexes": resend,
        "ocr_history_ids": ocr_ids,
        "passengers": passengers,
    }
