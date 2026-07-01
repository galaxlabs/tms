import frappe, re

def fix_retention_css(name):
    pf = frappe.get_doc("Print Format", name)
    css = pf.css

    old_rule = """\
.net-payable-row td {
  background: #ecfdf5;
  color: #065f46;
  font-weight: 700;
}"""

    new_rule = """\
.net-payable-row td,
.net-payable-row td:first-child,
.net-payable-row td:last-child {
  background: #ecfdf5 !important;
  color: #065f46 !important;
  font-weight: 700 !important;
  print-color-adjust: exact;
  -webkit-print-color-adjust: exact;
}"""

    old_ret_rule = """\
.retention-row td {
  border-top: 1px dashed #94a3b8;
  color: #92400e;
  font-weight: 700;
}"""

    new_ret_rule = """\
.retention-row td {
  border-top: 1px dashed #94a3b8;
  color: #92400e;
  font-weight: 700;
  print-color-adjust: exact;
  -webkit-print-color-adjust: exact;
}"""

    changed = False
    if old_rule in css:
        css = css.replace(old_rule, new_rule)
        changed = True
    # Also handle if it's been fixed already with the new format
    if old_ret_rule in css:
        css = css.replace(old_ret_rule, new_ret_rule)
        changed = True

    if changed:
        pf.css = css
        pf.save()
        print(f"✅ Updated {name}")
    else:
        print(f"⚠️  Could not find old rule in {name}")
        # Debug: show what the current rule looks like
        idx = css.find("net-payable-row")
        if idx >= 0:
            end = css.find("}", idx)
            print(f"  Current rule:\n{css[max(0,idx-20):end+1]}")
        else:
            print("  'net-payable-row' not found in CSS!")

def run():
    fix_retention_css("Profarma Invoice")
    fix_retention_css("ZATCA Dynamic")
