import frappe

def run():
    pf = frappe.get_doc("Print Format", "ZATCA Dynamic")
    html = pf.html
    
    old = """      <div><strong>In Words:</strong> {{ doc.in_words or "-" }}</div>"""
    new = """      <div><strong>In Words:</strong> {% if apply_retention and retention_amount > 0 %}{{ frappe.utils.money_in_words(net_payable_after_retention, doc.currency) }}{% else %}{{ doc.in_words or "-" }}{% endif %}</div>"""
    
    if old not in html:
        print("Pattern not found!")
        idx = html.find("In Words")
        if idx >= 0:
            print(html[idx:idx+80])
        return
    
    html = html.replace(old, new)
    pf.html = html
    pf.save()
    
    print("✅ In Words updated — uses net_payable_after_retention when retention is ON")
    
    # Verify
    pf2 = frappe.get_doc("Print Format", "ZATCA Dynamic")
    idx = pf2.html.find("In Words")
    print(pf2.html[idx:idx+200])
