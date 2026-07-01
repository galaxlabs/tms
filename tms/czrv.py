import frappe

def run():
    frappe.clear_cache()
    
    pf = frappe.get_doc("Print Format", "ZATCA Dynamic")
    html = pf.html
    
    # Check for money macro
    if "{% macro money" in html:
        idx = html.find("{% macro money")
        print("Money macro at:", idx)
        print(html[idx:idx+200])
    else:
        print("Money macro NOT FOUND!")
    
    # Check for retention variable definitions
    print("\n=== RETENTION VARIABLE DEFS ===")
    for var in ["apply_retention", "retention_percentage", "retention_amount", "net_payable_after_retention"]:
        idx = html.find("{% set " + var)
        if idx >= 0:
            print(f"  {var} at {idx}")
            print(repr(html[idx:idx+120]))
        else:
            print(f"  {var} NOT DEFINED")
    
    # Find where retention vars are first used
    print("\n=== RETENTION USAGE ===")
    idx = html.find("apply_retention")
    if idx >= 0:
        print(f"First use at {idx}:")
        print(repr(html[max(0,idx-150):idx+200]))
    
    # Check if retention vars are defined before the totals section
    totals_idx = html.find("Totals")
    retention_usages = []
    for var in ["apply_retention", "retention_amount", "retention_percentage", "net_payable_after_retention"]:
        pos = html.find(var)
        retention_usages.append((var, pos))
    
    print("\n=== ORDERING ===")
    for var, pos in sorted(retention_usages, key=lambda x: x[1]):
        print(f"  {var} at {pos}")
    
    print("\n\n=== PROFARMA RETENTION VARIABLES ===")
    pf2 = frappe.get_doc("Print Format", "Profarma Invoice")
    html2 = pf2.html
    for var in ["apply_retention", "retention_percentage", "retention_amount", "net_payable_after_retention"]:
        idx = html2.find("{% set " + var)
        if idx >= 0:
            print(f"  {var} at {idx}")
            print(repr(html2[idx:idx+120]))
        else:
            # Maybe it's defined differently
            idx2 = html2.find(var)
            if idx2 >= 0:
                print(f"  {var} referenced at {idx2}")
