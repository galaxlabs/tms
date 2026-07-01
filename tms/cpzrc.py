import frappe, re

RETENTION_CSS = """
.retention-row td {
  border-top: 1px dashed #94a3b8;
  color: #92400e;
  font-weight: 700;
}

.net-payable-row td {
  background: #ecfdf5;
  color: #065f46;
  font-weight: 700;
}
"""

def run():
    pf = frappe.get_doc("Print Format", "ZATCA Dynamic")
    css = pf.css

    # Check if retention CSS already exists
    if ".retention-row" in css and ".net-payable-row" in css:
        print("Retention CSS already exists - skipping")
        return

    # Insert after the totals-table tr:last-child td block
    pattern = r'(totals-table tr:last-child td \{[^}]*\})'
    match = re.search(pattern, css)
    if match:
        insertion_point = match.end()
        css = css[:insertion_point] + "\n" + RETENTION_CSS + css[insertion_point:]
        pf.css = css
        pf.save()
        print("Retention CSS added successfully to ZATCA Dynamic")
    else:
        print("Could not find totals-table tr:last-child td pattern")
        # Fallback: try to find a good insertion point
        idx = css.find("totals-table tr:last-child td")
        if idx >= 0:
            end_br = css.find("}", idx)
            if end_br >= 0:
                css = css[:end_br+1] + "\n" + RETENTION_CSS + css[end_br+1:]
                pf.css = css
                pf.save()
                print("Retention CSS added (fallback method)")
        else:
            print("Could not find insertion point at all!")
