import frappe, base64
from tms.utils.zatca_invoice import build_zatca_qr_payload

def run():
    # Check one invoice
    r = frappe.db.sql("""
        SELECT name, zatca_qr_payload
        FROM `tabSales Invoice`
        WHERE zatca_qr_payload IS NOT NULL AND zatca_qr_payload != ''
        ORDER BY modified DESC
        LIMIT 1
    """, as_dict=True)[0]
    
    doc = frappe.get_doc("Sales Invoice", r.name)
    new_payload = build_zatca_qr_payload(doc)
    
    # Decode both old and new
    old = base64.b64decode(r.zatca_qr_payload)
    new = base64.b64decode(new_payload)
    
    old_name = old[2:2+old[1]].decode('utf-8')
    new_name = new[2:2+new[1]].decode('utf-8')
    
    company = frappe.get_doc("Company", doc.company)
    print(f"Invoice: {r.name}")
    print(f"Company: {doc.company}")
    print(f"  company_name_arabic = '{company.company_name_arabic}'")
    print(f"  custom_company_name_arabic = '{company.custom_company_name_arabic}'")
    print(f"Old seller name in QR: '{old_name}'")
    print(f"New seller name in QR: '{new_name}'")
    
    # Check if they differ
    if old_name != new_name:
        print(f"\n✅ FIXED! Names differ - regeneration would work")
        # Now regenerate
        doc.db_set("zatca_qr_payload", new_payload, update_modified=False)
        print(f"✅ Regenerated for {r.name}")
    else:
        print(f"\n⚠️ Names are the same - fix might not have been loaded")
        # Check the actual module code
        import tms.utils.zatca_invoice as zi
        import inspect
        src = inspect.getsource(zi.build_zatca_qr_payload)
        # Find the seller_name part
        for line in src.split('\n'):
            if 'seller_name' in line or 'custom_company' in line or 'company_name_arabic' in line:
                print(f"  Code: {line.strip()}")
