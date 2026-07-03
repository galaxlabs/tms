import frappe, base64

def run():
    invoices = frappe.get_all(
        "Sales Invoice",
        filters={"docstatus": 1, "zatca_qr_payload": ["is", "set"]},
        fields=["name", "posting_date"],
        order_by="posting_date desc",
        limit=20
    )
    
    wrong_count = 0
    total = len(invoices)
    correct_name = "شركة التميز الشاملة الرائدة"
    
    for inv in invoices:
        try:
            doc = frappe.get_doc("Sales Invoice", inv.name)
            payload = doc.get("zatca_qr_payload", "")
            if not payload:
                continue
            decoded = base64.b64decode(payload).decode("utf-8")
            # Tag 1 is seller name (first byte is \x01, then length byte, then name)
            # Extract tag 1 value
            if decoded[0] == chr(1):
                name_len = ord(decoded[1])
                seller_name = decoded[2:2+name_len]
                if seller_name != correct_name:
                    wrong_count += 1
                    print(f"❌ {inv.name}: '{seller_name}'")
                else:
                    print(f"✅ {inv.name}: correct")
        except Exception as e:
            print(f"⚠️  {inv.name}: error - {e}")
    
    print(f"\nTotal checked: {total}")
    print(f"Wrong: {wrong_count}")
    print(f"Correct: {total - wrong_count}")
