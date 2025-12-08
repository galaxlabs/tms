# tms/utils/ocr_training_sync.py

from __future__ import annotations

import frappe
from typing import Any, Dict, List, Tuple, Optional


def _get_passenger_rows(trip_doc) -> List[Dict[str, Any]]:
    """
    Normalize passenger rows so we can support both:
    - full_name / id_no / nationality
    - passenger_name / idpassport_no / nationality
    """
    rows = []

    for row in getattr(trip_doc, "passengers", []):
        name_val = getattr(row, "full_name", None) or getattr(row, "passenger_name", None)
        id_val = getattr(row, "id_no", None) or getattr(row, "idpassport_no", None)
        nat_val = getattr(row, "nationality", None)

        rows.append(
            {
                "row": row,
                "name": (name_val or "").strip(),
                "id_no": (id_val or "").strip(),
                "nationality": (nat_val or "").strip(),
            }
        )
    return rows


def _find_matching_passenger(
    ocr_row: Dict[str, Any],
    passengers: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """
    Match OCR History entry to a passenger row:
    - Prefer ID match (exact, case-insensitive)
    - Fallback to name match (case-insensitive)
    """
    ocr_id = (ocr_row.get("id_no") or "").strip()
    ocr_name = (ocr_row.get("full_name") or ocr_row.get("name") or "").strip()

    # 1) ID match
    if ocr_id:
        for p in passengers:
            if p["id_no"] and p["id_no"].lower() == ocr_id.lower():
                return p

    # 2) Name match
    if ocr_name:
        ocr_name_lower = ocr_name.lower()
        for p in passengers:
            if p["name"] and p["name"].lower() == ocr_name_lower:
                return p

    return None


def _resolve_country_link(nationality_text: str) -> Optional[str]:
    """
    Try to map nationality text to a Country record.
    Works with both English and Arabic via LIKE.
    """
    if not nationality_text:
        return None

    nat = nationality_text.strip()
    # Try exact first
    name = frappe.db.get_value("Country", {"country_name": nat}, "name")
    if name:
        return name

    # Fuzzy LIKE
    name = frappe.db.get_value(
        "Country",
        {"country_name": ["like", f"%{nat}%"]},
        "name",
    )
    return name


def _training_example_exists(ocr_file: str, trip_name: str, passenger_name: str, id_no: str) -> bool:
    filters = {
        "trip": trip_name,
        "file": ocr_file,
        "full_name_correct": passenger_name,
        "id_no_correct": id_no,
    }
    return frappe.db.exists("OCR Training Example", filters) is not None


def create_training_examples_for_trip(trip_doc) -> int:
    """
    Main entry: called from Trip on_update / on_submit.

    For each OCR History row attached to this Trip:
    - Find matching passenger
    - Create OCR Training Example (if not already created)
    Returns number of examples created.
    """
    created = 0

    # 1) Get passengers snapshot
    passengers = _get_passenger_rows(trip_doc)
    if not passengers:
        return 0

    # 2) Fetch OCR History rows for this trip
    ocr_rows = frappe.get_all(
        "OCR History",
        filters={"trip": trip_doc.name},
        fields=[
            "name",
            "source",
            "ocr_engine",
            "confidence",
            "file",
            "raw_text",
            "fixed_text",
            "full_name",
            "id_no",
            "nationality",
        ],
        order_by="creation asc",
    )

    if not ocr_rows:
        return 0

    for o in ocr_rows:
        # Normalize OCR fields
        o_full_name = (o.get("full_name") or "").strip()
        o_id_no = (o.get("id_no") or "").strip()
        o_nat = (o.get("nationality") or "").strip()
        o_file = o.get("file")

        # Find passenger row that represents the final corrected data
        passenger = _find_matching_passenger(o, passengers)
        if not passenger:
            # If no match, skip – this avoids bad training data
            continue

        p_name = passenger["name"]
        p_id_no = passenger["id_no"]
        p_nat = passenger["nationality"]

        if not p_name and not p_id_no:
            # nothing useful to train on
            continue

        if not o_file:
            # training example should be tied to the File for traceability
            continue

        # Avoid duplicates
        if _training_example_exists(o_file, trip_doc.name, p_name, p_id_no):
            continue

        # Decide document type – for now, Passport by default, you can improve later
        document_type = "Passport"

        # Choose nationality text for Country mapping
        nat_text = p_nat or o_nat
        country_link = _resolve_country_link(nat_text) if nat_text else None

        # Build MRZ-like block – you can improve later
        mrz_block = (o.get("fixed_text") or o.get("raw_text") or "")[-200:]

        # Create OCR Training Example
        ex = frappe.get_doc(
            {
                "doctype": "OCR Training Example",
                "document_type": document_type,
                "country": country_link,
                "engine": o.get("ocr_engine") or "other",
                "status": "Approved",  # you can add a review workflow later
                "file": o_file,
                "trip": trip_doc.name,
                "raw_text": o.get("raw_text") or "",
                "mrz_block": mrz_block,
                "full_name_correct": p_name,
                "id_no_correct": p_id_no,
                "nationality_correct": nat_text,
                "extra_json": frappe.as_json(
                    {
                        "ocr_history": {
                            "name": o.get("name"),
                            "full_name": o_full_name,
                            "id_no": o_id_no,
                            "nationality": o_nat,
                            "confidence": o.get("confidence"),
                            "source": o.get("source"),
                        }
                    },
                    indent=2,
                ),
            }
        )
        ex.insert(ignore_permissions=True)
        created += 1

    return created


def backfill_training_examples_for_trip_name(trip_name: str) -> int:
    """
    Helper for bench console:
      from tms.utils.ocr_training_sync import backfill_training_examples_for_trip_name
      backfill_training_examples_for_trip_name("TRIP-0001")
    """
    trip = frappe.get_doc("Trip", trip_name)
    return create_training_examples_for_trip(trip)
