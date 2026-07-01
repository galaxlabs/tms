import frappe

def run():
    terms = ["%التميز%", "%الرائدة%"]

    for doctype in ["Customer", "Supplier", "Address"]:
        for term in terms:
            if doctype == "Customer":
                rows = frappe.db.sql("""
                    SELECT name, customer_name
                    FROM `tabCustomer`
                    WHERE customer_name LIKE %s
                """, (term,), as_dict=True)
            elif doctype == "Supplier":
                rows = frappe.db.sql("""
                    SELECT name, supplier_name
                    FROM `tabSupplier`
                    WHERE supplier_name LIKE %s
                """, (term,), as_dict=True)
            else:
                rows = frappe.db.sql("""
                    SELECT name, address_title
                    FROM `tabAddress`
                    WHERE address_title LIKE %s
                """, (term,), as_dict=True)

            if rows:
                print(f"\n{doctype} matching '{term.strip('%')}' ({len(rows)}):")
                for r in rows:
                    name = r.get("customer_name") or r.get("supplier_name") or r.get("address_title") or r.name
                    print(f"  {r.name} | {name}")

    # Sales Invoices
    for term in terms:
        sinv = frappe.db.sql("""
            SELECT DISTINCT name, customer_name
            FROM `tabSales Invoice`
            WHERE customer_name LIKE %s
            LIMIT 20
        """, (term,), as_dict=True)
        if sinv:
            print(f"\nSales Invoice matching '{term.strip('%')}' ({len(sinv)}):")
            for s in sinv:
                print(f"  {s.name} | {s.customer_name}")
