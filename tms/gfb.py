import frappe

def run():
    pf = frappe.get_doc("Print Format", "ZATCA Dynamic")
    html = pf.html
    idx = html.find("Paid Amount")
    # Go to end of this block (before bank-table or next div)
    idx2 = html.find("bank-table", idx)
    if idx2 < 0:
        idx2 = idx + 1000
    block = html[idx-50:idx2]
    print(repr(block))
