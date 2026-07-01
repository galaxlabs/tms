import frappe

def run():
    pf = frappe.get_doc("Print Format", "ZATCA Dynamic")
    css = pf.css
    
    # Find retention and net-payable CSS rules
    for keyword in ["retention", "net-payable", "last-child", "first-child", "print-color", "@media print"]:
        idx = css.find(keyword)
        if idx >= 0:
            # Find the enclosing rule
            start = css.rfind("\n", 0, idx)
            if start < 0:
                start = max(0, idx - 50)
            # Find end of rule (closing brace)
            end = css.find("}", idx)
            if end >= 0:
                end_rule = css.find("}", end + 1)
                if end_rule >= 0:
                    end = end_rule + 1
                else:
                    end += 1
            else:
                end = min(len(css), idx + 200)
            print(f"\n--- Found '{keyword}' at {idx} ---")
            print(css[start:end].strip())
            start_newline = css.rfind("/*", 0, idx)
            if start_newline >= 0:
                end_newline = css.find("*/", start_newline)
                if end_newline >= 0:
                    comment = css[start_newline:end_newline+2]
                    print(f"  [comment] {comment}")

