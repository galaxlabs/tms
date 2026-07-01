import frappe

def run():
    frappe.clear_cache()
    
    # Check Profarma totals section for retention display
    pf = frappe.get_doc("Print Format", "Profarma Invoice")
    html = pf.html
    
    # Find the totals section
    idx = html.find("net_payable_after_retention")
    if idx >= 0:
        print("=== PROFARMA RETENTION IN TOTALS ===")
        # Print 2000 chars around it
        start = max(0, idx - 300)
        end = min(len(html), idx + 1500)
        print(html[start:end])
    
    print("\n\n=== ZATCA DYNAMIC TOTALS SECTION ===")
    # Check ZATCA Dynamic
    pf2 = frappe.get_doc("Print Format", "ZATCA Dynamic")
    html2 = pf2.html
    
    # Check for retention
    for term in ["retent", "net_payable", "apply_retention"]:
        idx2 = html2.lower().find(term)
        if idx2 >= 0:
            print(f"\n'{term}' found at {idx2}:")
            print(html2[max(0,idx2-100):min(len(html2), idx2+200)])
        else:
            print(f"\n'{term}' not found")
    
    # Find the totals/VAT section
    idx2 = html2.find("Totals")
    if idx2 >= 0:
        print(f"\n\n=== ZATCA TOTALS CONTEXT ===")
        print(html2[max(0,idx2-200):min(len(html2), idx2+2000)])
