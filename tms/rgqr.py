import frappe, base64
from tms.utils.zatca_invoice import build_zatca_qr_payload

def run():
    doc = frappe.get_doc("Sales Invoice", "ACC-SINV-2026-00014")
    payload = build_zatca_qr_payload(doc)
    
    print(f"New payload: {payload}")
    
    decoded = base64.b64decode(payload).decode("utf-8")
    print(f"Decoded TLV: {repr(decoded)}")
    
    # Update the doc
    doc.db_set("zatca_qr_payload", payload, update_modified=False)
    print(f"\n✅ QR payload updated for ACC-SINV-2026-00014")
    print(f"   Old: grand_total = 69486.08")
    print(f"   New: net_payable_after_retention = 66464.87")
