import frappe

def run():
    frappe.clear_cache()
    pf = frappe.get_doc("Print Format", "Profarma Invoice")
    
    html = pf.html
    
    # Find retention section
    idx = html.find("Retention Values")
    if idx >= 0:
        print("=== PROFARMA RETENTION CODE ===")
        print(html[idx:min(len(html), idx+1500)])
    else:
        idx = html.find("apply_retention")
        if idx >= 0:
            print("=== RETENTION CODE (via apply_retention) ===")
            print(html[idx:min(len(html), idx+1500)])
    
    # Find ZATCA print formats  
    print("\n=== ZATCA PRINT FORMATS ===")
    formats = frappe.get_all("Print Format", filters={"name": ["like", "%ZATCA%"]}, pluck="name")
    for f in formats:
        print(f"  {f}")
    
    # Check custom retention fields
    print("\n=== CUSTOM RETENTION FIELDS ON SALES INVOICE ===")
    cf = frappe.get_all("Custom Field", 
        filters={"dt": "Sales Invoice"},
        fields=["fieldname", "label", "fieldtype"])
    for f in cf:
        fn = (f.fieldname or "").lower()
        if "retent" in fn or "retent" in (f.label or "").lower():
            print(f"  {f.fieldname} | {f.label} | {f.fieldtype}")
    
    print("\nSearching for any retention on Sales Invoice...")
    all_fields = frappe.get_meta("Sales Invoice").get("fields")
    for f in all_fields:
        fn = (f.fieldname or "").lower()
        fl = (f.label or "").lower()
        if "retent" in fn or "retent" in fl:
            print(f"  {f.fieldname} | {f.label} | {f.fieldtype}")
