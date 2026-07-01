import frappe

def run():
    company = frappe.get_doc("Company", "Al-Tamayuz Al-Shamela Al-Raida Company")
    
    print("=== Company Record ===")
    print(f"  company_name: {company.company_name}")
    print(f"  company_name_arabic: '{company.company_name_arabic}'")
    print(f"  custom_company_name_arabic: '{company.custom_company_name_arabic}'")
    
    # Check if company_name_arabic has a default or is auto-set
    meta = frappe.get_meta("Company")
    field = meta.get_field("company_name_arabic")
    if field:
        print(f"\n=== company_name_arabic field definition ===")
        print(f"  fieldtype: {field.fieldtype}")
        print(f"  default: '{field.default}'" if field.default else "  default: None")
        print(f"  depends_on: {field.depends_on}" if field.depends_on else "  depends_on: None")
        print(f"  fetch_from: {field.fetch_from}" if field.fetch_from else "  fetch_from: None")
        print(f"  options: {field.options}" if field.options else "  options: None")
    
    # Check custom_company_name_arabic field too
    custom_meta = frappe.get_meta("Company", cached=False)
    custom_field = None
    for f in custom_meta.get("fields", []):
        if f.fieldname == "custom_company_name_arabic":
            custom_field = f
            break
    if custom_field:
        print(f"\n=== custom_company_name_arabic field definition ===")
        print(f"  fieldtype: {custom_field.fieldtype}")
        print(f"  default: '{custom_field.default}'" if custom_field.default else "  default: None")
    
    # Check if there's any code that sets company_name_arabic automatically
    print("\n=== Checking for code that sets company_name_arabic ===")
    import subprocess
    result = subprocess.run(
        ["grep", "-r", "company_name_arabic", "/home/dg/dg-b/apps/", "--include=*.py", "-l"],
        capture_output=True, text=True, timeout=15
    )
    files = [f for f in result.stdout.strip().split('\n') if f and 'fql.py' not in f and 'ccn.py' not in f and 'fr2.py' not in f]
    for f in files:
        print(f"  {f}")
