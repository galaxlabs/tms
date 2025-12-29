import frappe

THRESHOLD = 0.80

def run():
    # Use the names printed from last step
    ocr_names = ['78q00u73kp', 'h9n77vmua5', 'h9nc81bves']

    rows = frappe.db.get_all(
        "OCR History",
        filters={"name": ["in", ocr_names]},
        fields=["name", "full_name", "id_no", "nationality", "confidence", "file"],
        order_by="processed_on asc"
    )

    bad = []
    for idx, r in enumerate(rows, start=1):
        conf = float(r.get("confidence") or 0)
        full_name = (r.get("full_name") or "").strip()
        id_no = (r.get("id_no") or "").strip()

        ok = (conf >= THRESHOLD) and bool(full_name) and bool(id_no)
        if not ok:
            bad.append({
                "passenger_index": idx,
                "ocr_history": r["name"],
                "confidence": conf,
                "missing": {
                    "full_name": not bool(full_name),
                    "id_no": not bool(id_no),
                }
            })

    print("TOTAL:", len(rows))
    print("BAD:", bad)

    if not bad:
        print("✅ All passengers OK. Proceed to ASK_ROUTE.")
    else:
        # How your WhatsApp reply should look
        indexes = [b["passenger_index"] for b in bad]
        print(f"⚠️ Ask user to resend passenger image(s): {indexes}")

if __name__ == "__main__":
    run()
