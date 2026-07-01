import frappe, os

def run():
    tms_path = frappe.get_module_path("tms")
    print(f"TMS path: {tms_path}")
    
    # Search for QR payload generation code
    import subprocess
    result = subprocess.run(
        ["grep", "-r", "zatca_qr_payload", tms_path, "--include=\".py\"", "-l"],
        capture_output=True, text=True, timeout=10
    )
    print(f"\nFiles with 'zatca_qr_payload':\n{result.stdout}")
    
    result2 = subprocess.run(
        ["grep", "-r", "company_name_arabic", tms_path, "--include=\".py\"", "-l"],
        capture_output=True, text=True, timeout=10
    )
    print(f"\nFiles with 'company_name_arabic':\n{result2.stdout}")
    
    result3 = subprocess.run(
        ["grep", "-r", "qr", tms_path, "--include=\".py\"", "-l"],
        capture_output=True, text=True, timeout=10
    )
    print(f"\nFiles with 'qr' in TMS:\n{result3.stdout}")
    
    # Also check zatca_integration app
    try:
        z_path = frappe.get_module_path("zatca_integration")
        result4 = subprocess.run(
            ["grep", "-r", "company_name_arabic", z_path, "--include=\".py\"", "-l"],
            capture_output=True, text=True, timeout=10
        )
        print(f"\nzatca_integration files with 'company_name_arabic':\n{result4.stdout}")
    except:
        pass
    
    # Check vehicle_ss app too
    try:
        v_path = frappe.get_module_path("vehicle_ss")
        result5 = subprocess.run(
            ["grep", "-r", "company_name_arabic", v_path, "--include=\".py\"", "-l"],
            capture_output=True, text=True, timeout=10
        )
        print(f"\nvehicle_ss files with 'company_name_arabic':\n{result5.stdout}")
    except:
        pass
