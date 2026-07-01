import frappe

def run():
    pf = frappe.get_doc("Print Format", "Profarma Invoice")
    css = pf.css
    
    old = ".net-payable-row td {\r\n  background: #ecfdf5;\r\n  color: #065f46;\r\n  font-size: 12px;\r\n  border-top: 1px solid #10b981;\r\n  border-bottom: 1px solid #10b981;\r\n}"
    
    new = """.net-payable-row td,
.net-payable-row td:first-child,
.net-payable-row td:last-child {
  background: #ecfdf5 !important;
  color: #065f46 !important;
  font-weight: 700 !important;
  font-size: 12px !important;
  border-top: 1px solid #10b981 !important;
  border-bottom: 1px solid #10b981 !important;
  print-color-adjust: exact;
  -webkit-print-color-adjust: exact;
}"""
    
    if old in css:
        css = css.replace(old, new)
        
        # Also fix the retention-row rule
        ret_old = ".retention-row td {\r\n  border-top: 1px dashed #94a3b8;\r\n  color: #92400e;\r\n  font-weight: 700;\r\n}"
        ret_new = """.retention-row td {
  border-top: 1px dashed #94a3b8;
  color: #92400e;
  font-weight: 700;
  print-color-adjust: exact;
  -webkit-print-color-adjust: exact;
}"""
        if ret_old in css:
            css = css.replace(ret_old, ret_new)
        
        pf.css = css
        pf.save()
        print("✅ Profarma Invoice updated")
    else:
        print("EXACT old rule not found!")
        # Print repr of the actual text around it
        idx = css.find("net-payable-row")
        if idx >= 0:
            end = css.find("}", idx)
            print(repr(css[idx:end+1]))
