import frappe

def run():
    terms = ["%شركة%التميز%", "%التميز%الشاملة%", "%الرائدة%", "%شاملة%"]

    for term in terms:
        rows = frappe.db.sql("""
            SELECT name, customer_name
            FROM `tabCustomer`
            WHERE customer_name LIKE %s
        """, (term,), as_dict=True)
        if rows:
            print(f"\nCustomer matching '{term.strip('%')}' ({len(rows)}):")
            for r in rows:
                print(f"  {r.name} | {r.customer_name}")

    print("\n--- All customers with 'شركة' ---")
    rows = frappe.db.sql("""
        SELECT name, customer_name, customer_primary_contact
        FROM `tabCustomer`
        WHERE customer_name LIKE '%شركة%'
        ORDER BY name
        LIMIT 30
    """, as_dict=True)
    for r in rows:
        print(f"  {r.name} | {r.customer_name}")
