import frappe
from tms.utils.bot_settings import get_settings

def write_passengers_and_finalize(trip, contact, lang):
    settings, _ = get_settings()
    threshold = float(settings.confidence_threshold or 0)

    if trip.get("passengers"):
        return  # avoid duplicates

    ocr_rows = frappe.get_all(
        "OCR History",
        filters={"trip": trip.name},
        fields=["full_name", "id_no", "nationality", "confidence"],
        order_by="creation asc",
    )

    count = 0
    for row in ocr_rows:
        name = (row.full_name or "").strip()
        id_no = (row.id_no or "").strip()
        nat = (row.nationality or "").strip()
        conf = float(row.confidence or 0)

        if conf > 1:
            conf = conf / 100

        if not name or not id_no:
            continue
        if threshold and conf < threshold:
            continue

        p = trip.append("passengers", {})
        p.passenger_name = name
        p.idpassport_no = id_no
        p.nationality = nat
        count += 1

    if count:
        trip.save(ignore_permissions=True)

    return count
