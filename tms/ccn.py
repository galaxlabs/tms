import frappe

def run():
    company = frappe.get_doc("Company", "Al-Tamayuz Al-Shamela Al-Raida Company")
    print("=== Company Details ===")
    print(f"  Name: {company.name}")
    print(f"  Company Name: {company.company_name}")
    
    # Check for Arabic name field
    arabic_fields = ["custom_company_name_arabic", "company_name_arabic"]
    for f in arabic_fields:
        if hasattr(company, f) and getattr(company, f):
            print(f"  {f}: {getattr(company, f)}")
    
    # Where does the QR code seller name come from?
    # Check the ZATCA integration settings
    try:
        zatca_settings = frappe.db.sql("""
            SELECT name FROM `tabZATCA Business Settings`
            LIMIT 5
        """, as_dict=True)
        if zatca_settings:
            for zs in zatca_settings:
                doc = frappe.get_doc("ZATCA Business Settings", zs.name)
                print(f"\n=== ZATCA Business Settings: {zs.name} ===")
                for f in doc.meta.fields:
                    val = doc.get(f.fieldname)
                    if val and f.fieldtype in ("Data", "Small Text", "Long Text"):
                        if len(str(val)) < 200:
                            print(f"  {f.fieldname}: {val}")
    except Exception as e:
        print(f"\n  No ZATCA Business Settings: {e}")
    
    # Also check zatca_integration app settings
    try:
        frappe.get_attr("zatca_integration")
        print("\n=== zatca_integration app found ===")
        zs = frappe.db.sql("""
            SELECT name FROM `tabZATCA Integration Settings`
            LIMIT 5
        """, as_dict=True)
        if zs:
            for z in zs:
                doc = frappe.get_doc("ZATCA Integration Settings", z.name)
                print(f"ZATCA Integration Settings: {z.name}")
                for f in doc.meta.fields:
                    val = doc.get(f.fieldname)
                    if val and f.fieldtype in ("Data", "Small Text", "Long Text", "Text"):
                        if len(str(val)) < 200:
                            print(f"  {f.fieldname}: {val}")
    except:
        print("\n  No ZATCA Integration Settings")
    
    # Check where QR payload is generated - look at zatca_qr_payload in Sales Invoice
    print("\n=== QR Payload generation ===")
    import inspect
    from frappe.utils import get_module
    try:
        # Try to find where ZATCA QR is generated in TMS app
        import tms
        module_path = tms.__path__[0]
        print(f"TMS app path: {module_path}")
    except:
        pass
