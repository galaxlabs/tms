import frappe

def run():
    pf = frappe.get_doc("Print Format", "ZATCA Dynamic")
    css = pf.css
    
    # Find the last-child td section
    idx = css.find("totals-table tr:last-child td")
    if idx >= 0:
        end_br = css.find("}", idx)
        if end_br >= 0:
            after = css[end_br:]
            # Check what comes right after the closing brace
            print(f"After last-child td }}:\n{after[:200]}")
