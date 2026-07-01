import frappe

def run():
    pf = frappe.get_doc("Print Format", "Celtco Quotation - No VAT")
    html = pf.html
    
    # Check for duplicate total_ns definitions
    count = html.count("set total_ns")
    print(f"total_ns definitions: {count}")
    
    if count > 1:
        # Find their positions
        pos1 = html.find("set total_ns = namespace(grand=0)")
        pos2 = html.find("set total_ns = namespace(grand=0)", pos1 + 1)
        print(f"Position 1: {pos1}")
        print(f"Position 2: {pos2}")
        print(repr(html[pos2-30:pos2+80]))
        
        # Remove the second one
        block_end = html.find("{% endfor %}", pos2) + len("{% endfor %}")
        duplicate = html[pos2-1:block_end+1]  # include surrounding whitespace
        print(f"Removing at {pos2}: {repr(duplicate[:100])}")
        html = html[:pos2-1] + html[block_end+1:]
    
    pf.html = html
    pf.save()
    print("Saved!")
    
    # Clear cache
    frappe.clear_cache()
    print("Cache cleared")
