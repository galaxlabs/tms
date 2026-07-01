import frappe, os

def run():
    # Check git for original version
    pf_path = "/home/dg/dg-b/apps/tms/tms/transport_management_system/print_format/zatca_dynamic/zatca_dynamic.json"
    
    if os.path.exists(pf_path + ".orig"):
        print("Backup file found!")
    
    # Check git log
    os.system(f"cd /home/dg/dg-b/apps/tms && git log --oneline -5 -- {pf_path}")
    
    # Show current status
    os.system(f"cd /home/dg/dg-b/apps/tms && git diff -- {pf_path}")
