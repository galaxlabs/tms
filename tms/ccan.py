import frappe

def run():
    # Get the company used in the invoice
    doc = frappe.get_doc("Sales Invoice", "ACC-SINV-2026-00014")
    company = frappe.get_doc("Company", doc.company)
    
    print(f"Company: {company.name}")
    print(f"  company_name: {company.company_name}")
    print(f"  company_name_arabic: {getattr(company, 'company_name_arabic', 'NOT SET')}")
    print(f"  custom_company_name_arabic: {getattr(company, 'custom_company_name_arabic', 'NOT SET')}")
    
    # Check what the QR builder uses
    from tms.utils.zatca_invoice import build_zatca_qr_payload
    payload = build_zatca_qr_payload(doc)
    import base64
    decoded = base64.b64decode(payload).decode("utf-8")
    print(f"\nCurrent QR seller name (tag 1): {decoded.split(chr(2))[0][1:] if chr(2) in decoded else 'unknown'}")
