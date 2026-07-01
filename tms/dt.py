import frappe

def run():
    pf = frappe.get_doc("Print Format", "Celtco Quotation - No VAT")
    html = pf.html
    
    # Print first 1500 chars to see the variable definitions
    print("=== FIRST 1500 CHARS ===")
    print(html[:1500])
    print("\n\n=== CHARS 9500-10500 ===")
    print(html[9500:10500])
