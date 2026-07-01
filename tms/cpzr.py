import frappe

def run():
    pf = frappe.get_doc("Print Format", "ZATCA Dynamic")
    css = pf.css
    
    # Find the totals table CSS area
    idx = css.find("totals-table")
    if idx >= 0:
        print("totals-table CSS found at:", idx)
        print(css[max(0, idx-200):min(len(css), idx+600)])
    
    # Also check if retention HTML exists in the body
    html = pf.html
    ridx = html.find("Retention")
    if ridx >= 0:
        print("\n--- Retention HTML found at", ridx, "---")
        print(html[max(0, ridx-200):min(len(html), ridx+400)])
