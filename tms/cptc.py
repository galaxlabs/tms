import frappe

def run():
    pf = frappe.get_doc("Print Format", "ZATCA Dynamic")
    css = pf.css
    
    # Search for totals-table td patterns
    for keyword in ["totals-table td:", "totals-table tr:last"]:
        idx = css.find(keyword)
        if idx >= 0:
            start = css.rfind("}", 0, idx)
            if start < 0:
                start = max(0, idx - 100)
            end = css.find("}", idx)
            next_end = css.find("}", end + 1) if end >= 0 else -1
            if next_end >= 0:
                end = next_end
            if end >= 0:
                end += 1
            else:
                end = min(len(css), idx + 300)
            print(f"\n--- Found '{keyword}' at {idx} ---")
            print(css[start:end].strip())
