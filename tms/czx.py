import frappe, json

def run():
    # Check what ZATCA/XML fields exist on Sales Invoice
    meta = frappe.get_meta("Sales Invoice")
    fields = [f for f in meta.fields if "zatca" in f.fieldname.lower() or "xml" in f.fieldname.lower() or "qr" in f.fieldname.lower() or "invoice_data" in f.fieldname.lower()]
    
    print("=== ZATCA/XML/QR fields on Sales Invoice ===")
    if fields:
        for f in fields:
            print(f"  {f.fieldname} ({f.fieldtype})")
    else:
        print("  No ZATCA/XML/QR fields found on Sales Invoice meta")
    
    # Also check custom fields
    customs = frappe.db.sql("""
        SELECT fieldname, fieldtype 
        FROM `tabCustom Field` 
        WHERE dt = 'Sales Invoice' 
        AND (fieldname LIKE '%zatca%' OR fieldname LIKE '%xml%' OR fieldname LIKE '%qr%' 
             OR fieldname LIKE '%invoice_data%' OR fieldname LIKE '%signed%')
    """, as_dict=True)
    
    print("\n=== Custom Fields ===")
    if customs:
        for f in customs:
            print(f"  {f.fieldname} ({f.fieldtype})")
    else:
        print("  None found")
    
    # Look at a recent Sales Invoice for any XML data
    invoice = frappe.db.sql("""
        SELECT name, customer_name, custom_zatca_submit_time
        FROM `tabSales Invoice`
        ORDER BY modified DESC
        LIMIT 1
    """, as_dict=True)
    
    if invoice:
        inv = invoice[0]
        print(f"\n=== Most recent invoice: {inv.name} ===")
        print(f"  Customer: {inv.customer_name}")
        print(f"  ZATCA submit time: {inv.custom_zatca_submit_time}")
        
        # Get all custom fields values for this invoice
        doc = frappe.get_doc("Sales Invoice", inv.name)
        
        # Check for any zatca/xml/signed data fields
        for f in meta.fields + customs:
            if hasattr(doc, f.fieldname):
                val = getattr(doc, f.fieldname)
                if val:
                    val_str = str(val)
                    if len(val_str) > 200:
                        val_str = val_str[:200] + "..."
                    print(f"\n  {f.fieldname}: {val_str}")
