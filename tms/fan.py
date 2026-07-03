import frappe

def run():
    company = frappe.get_doc("Company", "Al-Tamayuz Al-Shamela Al-Raida Company")
    
    print(f"Current:")
    print(f"  company_name_arabic: {company.company_name_arabic}")
    print(f"  custom_company_name_arabic: {getattr(company, 'custom_company_name_arabic', 'NOT SET')}")
    
    # Fix: set custom_company_name_arabic to match the full name
    company.db_set("custom_company_name_arabic", company.company_name_arabic)
    
    # Verify
    company2 = frappe.get_doc("Company", "Al-Tamayuz Al-Shamela Al-Raida Company")
    print(f"\nAfter fix:")
    print(f"  custom_company_name_arabic: {getattr(company2, 'custom_company_name_arabic', 'NOT SET')}")
    
    # Regenerate QR for the invoice
    doc = frappe.get_doc("Sales Invoice", "ACC-SINV-2026-00014")
    from tms.utils.zatca_invoice import build_zatca_qr_payload
    payload = build_zatca_qr_payload(doc)
    import base64
    decoded = base64.b64decode(payload).decode("utf-8")
    seller = decoded.split(chr(2))[0][1:] if chr(2) in decoded else "unknown"
    print(f"\nQR seller name now: {seller}")
    
    doc.db_set("zatca_qr_payload", payload, update_modified=False)
    print("✅ QR payload updated on invoice")
