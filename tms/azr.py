import frappe

def run():
    pf = frappe.get_doc("Print Format", "ZATCA Dynamic")
    html = pf.html

    # Find the insertion point: right after {%- endmacro %}
    endmacro_idx = html.find("{%- endmacro %}")
    insert_point = html.find("{% set has_vat", endmacro_idx)

    retention_vars = """{% set apply_retention = doc.get("apply_retention") %}
{% set retention_percentage = frappe.utils.flt(doc.get("retention_percentage") or 0, 2) %}
{% set retention_amount = frappe.utils.flt(doc.get("retention_amount") or 0, 2) %}

{% if apply_retention and retention_amount > 0 %}
  {% set invoice_total_for_retention = frappe.utils.flt(doc.rounded_total or doc.grand_total or 0, 2) %}
  {% set net_payable_after_retention = frappe.utils.flt(doc.get("net_payable_after_retention") or (invoice_total_for_retention - retention_amount), 2) %}
{% else %}
  {% set net_payable_after_retention = frappe.utils.flt(doc.rounded_total or doc.grand_total or 0, 2) %}
{% endif %}

"""

    if insert_point >= 0:
        html = html[:insert_point] + retention_vars + html[insert_point:]
        pf.html = html
        pf.save()
        print("Saved! Retention variables added to ZATCA Dynamic")
    else:
        print("Insert point not found")
        
    # Verify
    pf2 = frappe.get_doc("Print Format", "ZATCA Dynamic")
    for var in ["apply_retention", "retention_percentage", "retention_amount", "net_payable_after_retention"]:
        if "{% set " + var in pf2.html:
            print(f"  {var}: OK")
        else:
            print(f"  {var}: MISSING!")
