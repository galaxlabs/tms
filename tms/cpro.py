import frappe, json, subprocess, os

CSS_PATH = "tms/transport_management_system/print_format/zatca_dynamic/zatca_dynamic.json"
REPO = "/home/dg/dg-b/apps/tms"

RETENTION_VARS = """{% set apply_retention = doc.get("apply_retention") %}
{% set retention_percentage = frappe.utils.flt(doc.get("retention_percentage") or 0, 2) %}
{% set retention_amount = frappe.utils.flt(doc.get("retention_amount") or 0, 2) %}

{% if apply_retention and retention_amount > 0 %}
  {% set invoice_total_for_retention = frappe.utils.flt(doc.rounded_total or doc.grand_total or 0, 2) %}
  {% set net_payable_after_retention = frappe.utils.flt(doc.get("net_payable_after_retention") or (invoice_total_for_retention - retention_amount), 2) %}
{% else %}
  {% set net_payable_after_retention = frappe.utils.flt(doc.rounded_total or doc.grand_total or 0, 2) %}
{% endif %}

"""

RETENTION_ROWS = """            {% if apply_retention and retention_amount > 0 %}
              <tr class="retention-row">
                <td>Retention {{ retention_percentage }}%</td>
                <td class="num">- {{ money(retention_amount) }}</td>
              </tr>
              <tr class="net-payable-row">
                <td><strong>Net Payable After Retention</strong></td>
                <td class="num">
                  <strong>{{ money(net_payable_after_retention) }}</strong>
                </td>
              </tr>
              {% endif %}
            """

def run():
    # 1. Get original from git HEAD
    result = subprocess.run(
        ["git", "show", f"HEAD:{CSS_PATH}"],
        capture_output=True, text=True, cwd=REPO
    )
    if result.returncode != 0:
        print(f"Git error: {result.stderr}")
        return
    
    orig = json.loads(result.stdout)
    orig_css = orig["css"]
    orig_html = orig["html"]
    
    # 2. Build new HTML by injecting Jinja into original
    new_html = orig_html
    
    # Insert retention vars after the macro
    insert_after = "{%- endmacro %}"
    macro_idx = new_html.find(insert_after)
    if macro_idx >= 0:
        new_html = (new_html[:macro_idx + len(insert_after)] + 
                    "\n\n" + RETENTION_VARS + 
                    new_html[macro_idx + len(insert_after):])
        print("✓ Retention vars inserted")
    else:
        print("✗ Could not find endmacro!")
        return
    
    # Insert retention rows before '<tr><td>Outstanding</td>'
    outstanding = '<tr><td>Outstanding</td>'
    ot_idx = new_html.find(outstanding)
    if ot_idx >= 0:
        new_html = (new_html[:ot_idx] + RETENTION_ROWS + new_html[ot_idx:])
        print("✓ Retention rows inserted")
    else:
        print("✗ Could not find Outstanding row!")
        return
    
    # 3. Update print format in DB with original CSS + new HTML
    pf = frappe.get_doc("Print Format", "ZATCA Dynamic")
    pf.css = orig_css
    pf.html = new_html
    pf.save()
    
    # 4. Write updated JSON to disk
    orig["css"] = orig_css
    orig["html"] = new_html
    filepath = os.path.join(REPO, CSS_PATH)
    with open(filepath, "w") as f:
        json.dump(orig, f, indent=1, ensure_ascii=False)
    
    print("✅ ZATCA Dynamic restored with original CSS + Jinja retention only")
    
    # Verify
    pf2 = frappe.get_doc("Print Format", "ZATCA Dynamic")
    if "retention-row" in pf2.css:
        print("   ⚠️ retention-row still in CSS!")
    else:
        print("   ✅ No retention CSS classes")
    if "apply_retention" not in pf2.html:
        print("   ⚠️ apply_retention missing from HTML!")
    else:
        print("   ✅ Retention Jinja present in HTML")
