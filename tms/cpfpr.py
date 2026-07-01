import frappe

def run():
    pf = frappe.get_doc("Print Format", "Profarma Invoice")
    css = pf.css
    
    old = """.net-payable-row td {
  background: #ecfdf5;
  color: #065f46;
  font-size: 12px;
  border-top: 1px solid #10b981;
  border-bottom: 1px solid #10b981;
}"""
    
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
        # Also update the retention-row CSS to add print-color-adjust
        ret_old = """.retention-row td {
  border-top: 1px dashed #94a3b8;
  color: #92400e;
  font-weight: 700;
}"""
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
        print("Old rule not found. Current CSS:")
        idx = css.find("net-payable-row")
        if idx >= 0:
            end = css.find("}", idx)
            print(css[max(0, idx-50):end+1])
