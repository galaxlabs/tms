import frappe

def verify(name):
    pf = frappe.get_doc("Print Format", name)
    css = pf.css
    
    print(f"\n{'='*50}")
    print(f"  {name}")
    print(f"{'='*50}")
    
    idx = css.find("net-payable-row")
    if idx >= 0:
        end = css.find("}", idx)
        # Find all lines of the rule
        # Go backwards to find the start of the selector
        prev_semi = css.rfind(";", 0, idx)
        prev_close = css.rfind("}", 0, idx)
        start = max(prev_semi, prev_close) + 1
        start = css.find("net", start)  # find start of selector
        
        # Go forward past the last brace
        end2 = css.find("}", end + 1)  # might be multi-rule
        if end2 >= 0 and end2 - end < 5:
            end = end2
        print(f"  Rule:\n{css[start:end+1]}")
        
        # Check for print-color-adjust
        if "print-color-adjust: exact" in css[start:end+1]:
            print("  ✅ print-color-adjust: exact present")
        else:
            print("  ❌ print-color-adjust: exact MISSING")
        
        if "-webkit-print-color-adjust" in css[start:end+1]:
            print("  ✅ -webkit-print-color-adjust: exact present")
        else:
            print("  ❌ -webkit-print-color-adjust: exact MISSING")
        
        if "!important" in css[start:end+1]:
            print("  ✅ !important used")
        else:
            print("  ❌ !important MISSING")
    else:
        print("  ⚠️  net-payable-row not found in CSS!")

def run():
    verify("Profarma Invoice")
    verify("ZATCA Dynamic")
