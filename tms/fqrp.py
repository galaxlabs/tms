"""fix_qr_payload.py - change zatca QR to use net_payable_after_retention"""
import frappe

def run():
    path = frappe.get_app_path("tms", "utils", "zatca_invoice.py")
    with open(path, "r") as f:
        content = f.read()

    old = '    total_amount = f"{float(getattr(doc, \'grand_total\', 0) or 0):.2f}"'
    new = """    if doc.get("apply_retention") and doc.get("net_payable_after_retention"):
        total_amount = f"{float(doc.net_payable_after_retention):.2f}"
    else:
        total_amount = f"{float(doc.grand_total or 0):.2f}" """

    if old not in content:
        print("ERROR: old line not found in zatca_invoice.py!")
        # Find what's there
        if 'total_amount' in content:
            for i, line in enumerate(content.split('\n')):
                if 'total_amount' in line and 'grand_total' in line:
                    print(f"  Found at line {i+1}: {repr(line.strip())}")
        return

    content = content.replace(old, new)
    with open(path, "w") as f:
        f.write(content)

    print("✅ QR payload updated — uses net_payable_after_retention when retention enabled, else grand_total")
