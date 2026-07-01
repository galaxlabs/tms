import frappe

def run():
    pf = frappe.get_doc("Print Format", "ZATCA Dynamic")
    html = pf.html
    
    # Find the area after money macro and before HTML content
    idx = html.find("{%- endmacro %}")
    print("endmacro at", idx)
    print(repr(html[idx:min(len(html), idx+300)]))
    
    # Find where HTML starts
    for tag in ['<div class="invoice-shell">', '<div class="sheet">', '<div class="company-header-box">']:
        idx2 = html.find(tag)
        if idx2 >= 0:
            print(f"'{tag}' at {idx2}")
    
    # Check if any retention vars exist in the template
    for var in ["apply_retention", "retention_percentage", "retention_amount", "net_payable_after_retention", "invoice_total_for_retention"]:
        if "{% set " + var in html:
            print(f"'{var}' SET exists")
