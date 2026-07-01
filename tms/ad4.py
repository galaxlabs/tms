import frappe

def run():
    pf = frappe.get_doc("Print Format", "Celtco Quotation - No VAT")
    html = pf.html
    
    # Check for total_ns
    total_ns_count = html.count("total_ns")
    print("total_ns references:", total_ns_count)
    
    idx = html.find("set total_ns")
    if idx >= 0:
        print("{% set total_ns %} at", idx)
        print(repr(html[max(0,idx-50):idx+80]))
    else:
        print("{% set total_ns %} NOT FOUND!")
    
    # Check for quotation-shell
    idx2 = html.find("quotation-shell")
    if idx2 >= 0:
        print("\nBefore quotation-shell (", idx2, "):")
        print(repr(html[max(0,idx2-200):idx2]))
    
    # Find last endif
    idx3 = html.rfind("{% endif %}")
    print("\nLast endif at", idx3)
    if idx3 >= 0:
        print(repr(html[idx3:min(len(html), idx3+250)]))
    
    # Find money macro
    idx4 = html.find("{% macro money")
    if idx4 >= 0:
        end = html.find("{%- endmacro %}", idx4) + 20
        print("\nMoney macro at", idx4)
        print(repr(html[max(0,idx4-50):end]))
