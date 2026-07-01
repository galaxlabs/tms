import frappe

def run():
    pf = frappe.get_doc("Print Format", "ZATCA Dynamic")
    css = pf.css
    
    old = """.net-payable-row td,
.net-payable-row td:first-child,
.net-payable-row td:last-child {
  background: #ecfdf5 !important;
  color: #065f46 !important;
  font-weight: 700 !important;
  print-color-adjust: exact;
  -webkit-print-color-adjust: exact;
}"""
    
    new = """.net-payable-row td,
.net-payable-row td:first-child,
.net-payable-row td:last-child {
  background: #065f46 !important;
  color: white !important;
  font-weight: 700 !important;
  print-color-adjust: exact;
  -webkit-print-color-adjust: exact;
}"""
    
    if old in css:
        css = css.replace(old, new)
        pf.css = css
        pf.save()
        print("✅ ZATCA Dynamic updated (dark green bg, white text)")
    else:
        print("Old rule not found - checking current CSS...")
        idx = css.find("net-payable-row")
        if idx >= 0:
            end = css.find("}", idx)
            # Find the actual start
            start = css.rfind("}", 0, idx)
            if start < 0:
                start = 0
            print(repr(css[start:end+1]))
