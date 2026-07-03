import frappe

def run():
    pf = frappe.get_doc("Print Format", "ZATCA Dynamic")
    html = pf.html
    # Get exact retention block
    idx = html.find("Paid Amount")
    if idx >= 0:
        # Print the 100 chars before and after this point
        before = html[idx-50:idx]
        after = html[idx:idx+500]
        print("BEFORE:", repr(before))
        print("AFTER:", repr(after[:300]))
        print("===FULL BLOCK===")
        print(after)
