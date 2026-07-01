import frappe, base64

def run():
    # Find all invoices with old payload containing للنقل
    results = frappe.db.sql("""
        SELECT name, zatca_qr_payload
        FROM `tabSales Invoice`
        WHERE zatca_qr_payload IS NOT NULL AND zatca_qr_payload != ''
    """, as_dict=True)
    
    fixed = 0
    for r in results:
        try:
            raw = base64.b64decode(r.zatca_qr_payload)
        except:
            continue
        # Check tag 1 (seller name) for للنقل
        if len(raw) > 2:
            name_len = raw[1]
            seller_name = raw[2:2+name_len].decode('utf-8', errors='replace')
            if 'النقل' in seller_name:
                doc = frappe.get_doc("Sales Invoice", r.name)
                from tms.utils.zatca_invoice import build_zatca_qr_payload
                new_payload = build_zatca_qr_payload(doc)
                doc.db_set("zatca_qr_payload", new_payload, update_modified=False)
                fixed += 1
                print(f"  ✅ {r.name}: '{seller_name}' → regenerated")
    
    print(f"\nFixed: {fixed} invoices")

    # Also check print formats if they render QR from payload
    print("\n=== Checking if print formats need regeneration ===")
    print("The print formats read `doc.zatca_qr_payload` dynamically,")
    print("so updating the payload field is sufficient. No PDF/print regeneration needed.")
    print("The QR code image will be generated from the new payload on next print.")
