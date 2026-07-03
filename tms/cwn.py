import frappe, base64

def run():
    correct_name = "شركة التميز الشاملة الرائدة"
    
    invoices = frappe.get_all(
        "Sales Invoice",
        filters={"docstatus": 1, "zatca_qr_payload": ["is", "set"]},
        fields=["name", "posting_date"],
        order_by="posting_date desc"
    )
    
    total = len(invoices)
    wrong = []
    
    for inv in invoices:
        doc = frappe.get_doc("Sales Invoice", inv.name)
        payload = doc.get("zatca_qr_payload", "")
        if not payload:
            continue
        try:
            decoded = base64.b64decode(payload)
            # Parse TLV
            i = 0
            while i < len(decoded):
                tag = decoded[i]
                i += 1
                if i >= len(decoded): break
                length = decoded[i]
                i += 1
                if i + length > len(decoded): break
                value = decoded[i:i+length].decode("utf-8", errors="replace")
                if tag == 1:  # seller name
                    if value != correct_name:
                        wrong.append((inv.name, value, inv.posting_date))
                i += length
        except:
            wrong.append((inv.name, "PARSE_ERROR", inv.posting_date))
    
    print(f"Total invoices with QR payload: {total}")
    print(f"Correct name: {total - len(wrong)}")
    print(f"Wrong name: {len(wrong)}")
    
    if wrong:
        print(f"\nWrong invoices:")
        for name, val, date in wrong:
            print(f"  ❌ {name} ({date}): '{val[:50]}'")
