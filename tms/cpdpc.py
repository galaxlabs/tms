import frappe

def run():
    pf = frappe.get_doc("Print Format", "Profarma Invoice")
    css = pf.css
    
    idx = css.find("net-payable-row")
    if idx >= 0:
        end = css.find("}", idx)
        snippet = css[max(0, idx-50):end+1]
        print(repr(snippet))
