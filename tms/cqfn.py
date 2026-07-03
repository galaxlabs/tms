import frappe

def run():
    meta = frappe.get_meta("Sales Invoice")
    fields = ["zatca_qr_payload", "custom_zatca_qr_payload", "qr_payload", "custom_qr_payload", "custom_zatca_qr"]
    for f in fields:
        df = meta.get_field(f)
        if df:
            print(f"  ✅ '{f}' exists — type: {df.fieldtype}, label: {df.fieldname}")
        else:
            print(f"  ❌ '{f}' — NOT FOUND")
