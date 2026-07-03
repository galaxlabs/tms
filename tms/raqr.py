import frappe, base64
from tms.utils.zatca_invoice import build_zatca_qr_payload

def run():
    invoices = frappe.get_all(
        "Sales Invoice",
        filters={"docstatus": 1, "zatca_qr_payload": ["is", "set"]},
        fields=["name"],
        order_by="posting_date desc",
        limit=1000
    )
    
    correct_name = "شركة التميز الشاملة الرائدة"
    updated = 0
    skipped = 0
    wrong_before = 0
    
    for inv in invoices:
        doc = frappe.get_doc("Sales Invoice", inv.name)
        old_payload = doc.zatca_qr_payload or ""
        
        # Check old name
        try:
            raw = base64.b64decode(old_payload)
            if raw[0] == 1:
                old_seller = raw[2:2+raw[1]].decode("utf-8", errors="replace")
                if old_seller != correct_name:
                    wrong_before += 1
        except:
            pass
        
        # Build new payload
        new_payload = build_zatca_qr_payload(doc)
        
        if new_payload != old_payload:
            doc.db_set("zatca_qr_payload", new_payload, update_modified=False)
            updated += 1
        else:
            skipped += 1
    
    print(f"Total invoices with QR: {len(invoices)}")
    print(f"Had wrong name before: {wrong_before}")
    print(f"Updated: {updated}")
    print(f"Skipped (already correct): {skipped}")
    
    # Verify a sample
    if invoices:
        sample = frappe.get_doc("Sales Invoice", invoices[0].name)
        raw = base64.b64decode(sample.zatca_qr_payload)
        seller = raw[2:2+raw[1]].decode("utf-8")
        print(f"\nSample verification - {invoices[0].name}:")
        print(f"  Seller name: {seller}")
        print(f"  Correct: {seller == correct_name}")
