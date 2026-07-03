import frappe, base64, struct

def parse_tlv(data):
    """Parse TLV (Tag-Length-Value) encoded data."""
    result = {}
    i = 0
    while i < len(data):
        tag = data[i]
        i += 1
        if i >= len(data):
            break
        length = data[i]
        i += 1
        if i + length > len(data):
            break
        value = data[i:i+length]
        result[tag] = value.decode("utf-8", errors="replace")
        i += length
    return result

def run():
    # Count how many have payload
    total_inv = frappe.db.count("Sales Invoice", {"docstatus": 1})
    with_payload = frappe.db.count("Sales Invoice", {"docstatus": 1, "zatca_qr_payload": ["is", "set"]})
    print(f"Total submitted invoices: {total_inv}")
    print(f"With QR payload: {with_payload}\n")
    
    if with_payload == 0:
        return
    
    invoices = frappe.get_all(
        "Sales Invoice",
        filters={"docstatus": 1, "zatca_qr_payload": ["is", "set"]},
        fields=["name", "posting_date"],
        order_by="posting_date desc",
        limit=50
    )
    
    correct_name = "شركة التميز الشاملة الرائدة"
    wrong = []
    
    for inv in invoices:
        doc = frappe.get_doc("Sales Invoice", inv.name)
        payload = doc.get("zatca_qr_payload", "")
        if not payload:
            continue
        try:
            decoded = base64.b64decode(payload)
            tlv = parse_tlv(decoded)
            seller = tlv.get(1, "NOT FOUND")
            if seller != correct_name:
                wrong.append((inv.name, seller))
        except Exception as e:
            wrong.append((inv.name, f"PARSE ERROR: {e}"))
    
    print(f"Checked: {len(invoices)}")
    print(f"Correct: {len(invoices) - len(wrong)}")
    print(f"Wrong: {len(wrong)}")
    
    for name, seller in wrong[:10]:
        print(f"  ❌ {name}: '{seller[:60]}'")
