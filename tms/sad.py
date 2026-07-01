import frappe

def run():
    # Search ALL tables for any mention of التميز
    # First check all DocTypes that might have it
    terms = ["%التميز%", "%الرائدة%"]
    
    for dt in ["Supplier", "Address", "Sales Invoice", "Delivery Note", 
               "Vehicle", "Driver", "Mode of Transport", "Transportation Order",
               "Project", "Task", "Contact", "Lead", "Opportunity"]:
        try:
            meta = frappe.get_meta(dt)
            text_fields = [f.fieldname for f in meta.fields if f.fieldtype in ("Data", "Text", "Small Text", "Long Text", "Text Editor")]
        except:
            text_fields = []
        
        if not text_fields:
            continue
            
        for term in terms:
            conditions = " OR ".join([f"`{f}` LIKE %s" for f in text_fields])
            params = [term] * len(text_fields)
            try:
                rows = frappe.db.sql(f"""
                    SELECT name FROM `tab{dt}`
                    WHERE {conditions}
                    LIMIT 5
                """, params, as_dict=True)
                if rows:
                    print(f"{dt} ('{term.strip('%')}'): {[r.name for r in rows]}")
            except Exception as e:
                pass  # skip doctypes with issues

    # Also check for النقل in sales invoice items
    print("\n--- Sales Invoice items with 'نقل' ---")
    items = frappe.db.sql("""
        SELECT DISTINCT si.name, si.customer_name
        FROM `tabSales Invoice` si
        JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
        WHERE sii.item_name LIKE '%نقل%' OR sii.description LIKE '%نقل%'
        LIMIT 10
    """, as_dict=True)
    for r in items:
        print(f"  {r.name} | {r.customer_name}")
