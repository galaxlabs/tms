import frappe

def run():
    for name in ["Profarma Invoice", "ZATCA Dynamic"]:
        pf = frappe.get_doc("Print Format", name)
        css = pf.css
        has_retention_row = ".retention-row" in css or "retention" in css.lower()
        has_payable_row = ".net-payable" in css
        print(f"{name}: retention-row CSS={has_retention_row}, net-payable CSS={has_payable_row}")
        
        # Print any retention-related CSS
        idx = css.lower().find("retention")
        if idx >= 0:
            print(f"  CSS retention at {idx}:")
            print(css[max(0,idx-50):min(len(css), idx+150)])
