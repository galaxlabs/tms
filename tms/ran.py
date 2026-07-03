import frappe, base64
from tms.utils.zatca_invoice import build_zatca_qr_payload

def run():
    company = frappe.get_doc("Company", "Al-Tamayuz Al-Shamela Al-Raida Company")
    # Revert custom_company_name_arabic back to the shorter name
    company.db_set("custom_company_name_arabic", "شركة التميز الشاملة الرائدة")
    print(f"✅ Restored custom_company_name_arabic to: شركة التميز الشاملة الرائدة")
    
    # Regenerate QR for invoice
    doc = frappe.get_doc("Sales Invoice", "ACC-SINV-2026-00014")
    payload = build_zatca_qr_payload(doc)
    decoded = base64.b64decode(payload).decode("utf-8")
    seller = decoded.split(chr(2))[0][1:] if chr(2) in decoded else "unknown"
    print(f"QR seller name (tag 1): {seller}")
    
    doc.db_set("zatca_qr_payload", payload, update_modified=False)
    print("✅ QR payload updated on invoice")
