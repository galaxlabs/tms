import frappe, base64
from tms.utils.zatca_invoice import build_zatca_qr_payload

def run():
    invoices = frappe.db.sql("""
        SELECT name
        FROM `tabSales Invoice`
        WHERE zatca_qr_payload IS NOT NULL AND zatca_qr_payload != ''
        ORDER BY modified DESC
    """, as_dict=True)
    
    print(f"Total invoices with QR payload: {len(invoices)}")
    
    fixed = 0
    skipped = 0
    for r in invoices:
        try:
            doc = frappe.get_doc("Sales Invoice", r.name)
            old_payload = doc.zatca_qr_payload
            raw = base64.b64decode(old_payload)
            old_name = raw[2:2+raw[1]].decode('utf-8')
            
            # Check for نقل (transport) in the name
            if 'نقل' in old_name:
                new_payload = build_zatca_qr_payload(doc)
                new_raw = base64.b64decode(new_payload)
                new_name = new_raw[2:2+new_raw[1]].decode('utf-8')
                doc.db_set("zatca_qr_payload", new_payload, update_modified=False)
                fixed += 1
                print(f"✅ {r.name}: '{old_name}' → '{new_name}'")
            else:
                skipped += 1
        except Exception as e:
            print(f"⚠️ {r.name}: {e}")
    
    print(f"\nDone! Fixed: {fixed}, Skipped (no نقل): {skipped}, Total: {len(invoices)}")
