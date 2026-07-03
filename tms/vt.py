import frappe

def run():
    pf = frappe.get_doc("Print Format", "ZATCA Dynamic")
    html = pf.html
    idx = html.find("totals-table")
    idx2 = html.find("bank-table", idx)
    print(html[idx:idx2 if idx2 > 0 else idx + 2000])
