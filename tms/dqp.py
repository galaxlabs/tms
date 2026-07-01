import frappe, base64

def run():
    # Get a recent invoice with ZATCA QR payload
    inv = frappe.db.sql("""
        SELECT name, customer_name
        FROM `tabSales Invoice`
        WHERE zatca_qr_payload IS NOT NULL AND zatca_qr_payload != ''
        ORDER BY modified DESC
        LIMIT 3
    """, as_dict=True)
    
    for r in inv:
        doc = frappe.get_doc("Sales Invoice", r.name)
        payload = doc.get("zatca_qr_payload", "")
        print(f"\n=== {r.name} ===")
        print(f"Customer: {r.customer_name}")
        try:
            raw = base64.b64decode(payload)
            print(f"Raw bytes ({len(raw)}): {raw}")
            # Parse TLV: Tag(1 byte) + Length(1 byte) + Value(Length bytes)
            i = 0
            tags = {1: "Seller Name", 2: "VAT Number", 3: "Time Stamp", 4: "Invoice Total", 5: "VAT Total"}
            while i < len(raw):
                tag = raw[i]
                length = raw[i+1]
                value = raw[i+2:i+2+length]
                try:
                    decoded = value.decode('utf-8')
                except:
                    decoded = str(value)
                print(f"  Tag {tag} ({tags.get(tag, '?')}): {decoded}")
                i += 2 + length
        except Exception as e:
            print(f"  Decode error: {e}")

    # Also check if there's XML attached (custom_invoice_xml is an Attach field)
    print("\n\n=== Checking for attached XML files ===")
    for r in inv:
        doc = frappe.get_doc("Sales Invoice", r.name)
        xml_field = doc.get("custom_invoice_xml")
        if xml_field:
            print(f"{r.name}: custom_invoice_xml = {xml_field}")
            # Try to read the file
            try:
                file_doc = frappe.get_doc("File", {"file_url": xml_field})
                content = file_doc.get_content()
                print(f"  File content (first 500 chars):\n  {content[:500]}")
            except Exception as e:
                print(f"  Error reading file: {e}")
        else:
            print(f"{r.name}: no XML file attached")
