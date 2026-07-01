import frappe

def run():
    pf = frappe.get_doc("Print Format", "Celtco Quotation - No VAT")
    html = pf.html
    
    # Find quotation-shell location
    idx = html.find('<div class="quotation-shell">')
    print("quotation-shell at:", idx)
    
    # Find the last {% endif %} before quotation-shell (payment terms endif)
    before_shell = html[:idx]
    last_endif = before_shell.rfind("{% endif %}")
    print("Last endif before shell at:", last_endif)
    print(repr(html[last_endif:last_endif+150]))
    
    # Find if there's already a money macro anywhere
    macro_idx = html.find("{% macro money")
    print("\nMoney macro at:", macro_idx)
    
    # Remove the misplaced money macro
    if macro_idx >= 0:
        macro_end = html.find("{%- endmacro %}", macro_idx) + len("{%- endmacro %}")
        # Check what's between macro_end and quotation-shell
        between = html[macro_end:idx]
        print(f"\nBetween macro({macro_end}) and shell({idx}):")
        print(repr(between[:100]))
