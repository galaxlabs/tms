import frappe

def run():
    pf = frappe.get_doc("Print Format", "Celtco Quotation - No VAT")
    html = pf.html
    
    # Search for quotation without the full class
    for term in ["quotation-shell", "quotation", "shell", "company-header-box", "sheet", "class=\"sheet\""]:
        idx = html.find(term)
        if idx >= 0:
            print(f"'{term}' found at {idx}")
        else:
            print(f"'{term}' NOT FOUND")
    
    # Print first 300 chars
    print("\nTemplate start:")
    print(repr(html[:300]))
