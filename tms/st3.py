import frappe

def run():
    term = "%التميز%"
    term2 = "%الرائدة%"
    
    results = {}

    # Customers
    customers = frappe.db.sql("""
        SELECT name, customer_name, customer_name_in_arabic
        FROM `tabCustomer`
        WHERE customer_name LIKE %s OR customer_name_in_arabic LIKE %s
    """, (term, term), as_dict=True)
    results["Customer"] = [(c.name, c.customer_name, c.customer_name_in_arabic) for c in customers]

    if not customers:
        customers = frappe.db.sql("""
            SELECT name, customer_name
            FROM `tabCustomer`
            WHERE customer_name LIKE %s
        """, (term2,), as_dict=True)
        results["Customer"] = [(c.name, c.customer_name, "") for c in customers]

    # Suppliers (no arabic field)
    suppliers = frappe.db.sql("""
        SELECT name, supplier_name
        FROM `tabSupplier`
        WHERE supplier_name LIKE %s
    """, (term,), as_dict=True)
    results["Supplier"] = [(s.name, s.supplier_name, "") for s in suppliers]

    if not suppliers:
        suppliers = frappe.db.sql("""
            SELECT name, supplier_name
            FROM `tabSupplier`
            WHERE supplier_name LIKE %s
        """, (term2,), as_dict=True)
        results["Supplier"] = [(s.name, s.supplier_name, "") for s in suppliers]

    # Addresses
    addrs = frappe.db.sql("""
        SELECT name, address_title, address_line1, city
        FROM `tabAddress`
        WHERE address_title LIKE %s
    """, (term,), as_dict=True)
    results["Address"] = [(a.name, a.address_title, a.city) for a in addrs]

    if not addrs:
        addrs = frappe.db.sql("""
            SELECT name, address_title, address_line1, city
            FROM `tabAddress`
            WHERE address_title LIKE %s
        """, (term2,), as_dict=True)
        results["Address"] = [(a.name, a.address_title, a.city) for a in addrs]

    # Sales Invoices
    sinv = frappe.db.sql("""
        SELECT DISTINCT name, customer, customer_name
        FROM `tabSales Invoice`
        WHERE customer_name LIKE %s OR customer_name_in_arabic LIKE %s
        LIMIT 15
    """, (term, term), as_dict=True)
    results["Sales Invoice"] = [(s.name, s.customer, s.customer_name) for s in sinv]

    if not sinv:
        sinv = frappe.db.sql("""
            SELECT DISTINCT name, customer, customer_name
            FROM `tabSales Invoice`
            WHERE customer_name LIKE %s
            LIMIT 15
        """, (term2,), as_dict=True)
        results["Sales Invoice"] = [(s.name, s.customer, s.customer_name) for s in sinv]

    print("=== Search Results ===")
    for dt, rows in results.items():
        print(f"\n{dt} ({len(rows)}):")
        if rows:
            for r in rows:
                print("  " + " | ".join(str(x or "-") for x in r))
        else:
            print("  (none)")
