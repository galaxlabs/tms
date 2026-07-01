import frappe

def run():
    term = "التميز"
    results = {}

    # Customers
    customers = frappe.db.sql("""
        SELECT name, customer_name, customer_name_in_arabic
        FROM `tabCustomer`
        WHERE customer_name LIKE %s OR customer_name_in_arabic LIKE %s
    """, (f"%{term}%", f"%{term}%"), as_dict=True)
    results["Customer"] = [(c.name, c.customer_name, c.customer_name_in_arabic) for c in customers]

    # Suppliers
    suppliers = frappe.db.sql("""
        SELECT name, supplier_name, supplier_name_in_arabic
        FROM `tabSupplier`
        WHERE supplier_name LIKE %s OR supplier_name_in_arabic LIKE %s
    """, (f"%{term}%", f"%{term}%"), as_dict=True)
    results["Supplier"] = [(s.name, s.supplier_name, s.supplier_name_in_arabic or "-") for s in suppliers]

    # Addresses
    addrs = frappe.db.sql("""
        SELECT name, address_title, address_line1, city
        FROM `tabAddress`
        WHERE address_title LIKE %s
    """, (f"%{term}%",), as_dict=True)
    results["Address"] = [(a.name, a.address_title, a.city) for a in addrs]

    print(f"=== Searching for '{term}' ===")
    for dt, rows in results.items():
        print(f"\n--- {dt} ({len(rows)}) ---")
        if rows:
            for r in rows:
                print(" | ".join(str(x) for x in r))
        else:
            print("  None found")
