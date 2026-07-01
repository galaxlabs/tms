import frappe

def check_format(name):
    pf = frappe.get_doc("Print Format", name)
    html = pf.html
    css = pf.css
    
    checks = {
        "retention vars ({% set ... retention)": False,
        "Retention HTML": False,
        "Net Payable HTML": False,
        "retention-row CSS": False,
        "net-payable-row CSS": False,
    }
    
    # Check variable definitions for retention
    if "retention_percentage" in html and "retention_amount" in html:
        checks["retention vars ({% set ... retention)"] = True
    
    # Check HTML
    if 'class="retention-row"' in html:
        checks["Retention HTML"] = True
    if 'class="net-payable-row"' in html:
        checks["Net Payable HTML"] = True
    
    # Check CSS
    if ".retention-row" in css:
        checks["retention-row CSS"] = True
    if ".net-payable-row" in css:
        checks["net-payable-row CSS"] = True
    
    print(f"\n{'='*50}")
    print(f"  {name}")
    print(f"{'='*50}")
    all_ok = True
    for check, ok in checks.items():
        status = "✓" if ok else "✗"
        print(f"  {status} {check}")
        if not ok:
            all_ok = False
    if all_ok:
        print(f"\n  ✅ ALL CHECKS PASSED")
    else:
        print(f"\n  ❌ SOME CHECKS FAILED")
    return all_ok

def run():
    check_format("Profarma Invoice")
    check_format("ZATCA Dynamic")
