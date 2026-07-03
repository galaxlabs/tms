import frappe

def run():
    pf = frappe.get_doc("Print Format", "ZATCA Dynamic")
    html = pf.html
    css = pf.css
    
    # The current retention block and commented out rows need to be replaced
    old_totals = """            {% if doc.discount_amount %}
            <tr><td>Discount</td><td class="num">{{ money(doc.discount_amount) }}</td></tr>
            {% endif %}
            <tr><td>Total excl. VAT</td><td class="num">{{ money(doc.total) }}</td></tr>
            <tr><td>Total VAT</td><td class="num">{{ money(doc.total_taxes_and_charges) }}</td></tr>
            <!--<tr><td>Paid Amount</td><td class="num">{{ money(doc.paid_amount or 0) }}</td></tr>-->
                        {% if apply_retention and retention_amount > 0 %}
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
            <!--<tr><td>Outstanding</td><td class="num">{{ money(doc.outstanding_amount) }}</td></tr>-->
            <!--<tr><td>Grand Total</td><td class="num">{{ money(doc.grand_total) }}</td></tr>-->"""
    
    new_totals = """            {% if doc.discount_amount %}
            <tr><td>Discount</td><td class="num">{{ money(doc.discount_amount) }}</td></tr>
            {% endif %}
            <tr><td>Total excl. VAT</td><td class="num">{{ money(doc.total) }}</td></tr>
            <tr><td>Total VAT</td><td class="num">{{ money(doc.total_taxes_and_charges) }}</td></tr>
            {% if apply_retention and retention_amount > 0 %}
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
              <tr><td>Outstanding</td><td class="num">{{ money(net_payable_after_retention) }}</td></tr>
            {% else %}
              <tr><td>Outstanding</td><td class="num">{{ money(doc.outstanding_amount) }}</td></tr>
            {% endif %}
            <tr><td>Grand Total</td><td class="num">{{ money(doc.grand_total) }}</td></tr>"""
    
    if old_totals not in html:
        print("Old section not found exactly!")
        # Debug: show what's there
        idx = html.find("doc.discount_amount")
        if idx >= 0:
            end = html.find("bank-table", idx)
            print(html[idx:end if end > 0 else idx + 1500])
        return
    
    html = html.replace(old_totals, new_totals)
    pf.html = html
    
    # Also need to add CSS for retention-row and net-payable-row
    # Add after .totals-table tr:last-child td
    retention_css = """
.retention-row td {
  border-top: 1px dashed #94a3b8;
  color: #92400e;
  font-weight: 700;
  print-color-adjust: exact;
  -webkit-print-color-adjust: exact;
}

.net-payable-row td,
.net-payable-row td:first-child,
.net-payable-row td:last-child {
  background: var(--brand) !important;
  color: white !important;
  font-weight: 700 !important;
  print-color-adjust: exact;
  -webkit-print-color-adjust: exact;
}
"""
    
    if ".net-payable-row" not in css:
        idx_css = css.find("totals-table tr:last-child td")
        if idx_css >= 0:
            end_brace = css.find("}", idx_css)
            if end_brace >= 0:
                css = css[:end_brace+1] + retention_css + css[end_brace+1:]
                pf.css = css
    
    pf.save()
    print("✅ ZATCA Dynamic retention logic updated")
    
    # Verify
    pf2 = frappe.get_doc("Print Format", "ZATCA Dynamic")
    if ".net-payable-row" in pf2.css:
        print("   ✅ retention CSS present")
    if "Net Payable After Retention" in pf2.html and "Grand Total" in pf2.html:
        print("   ✅ Retention + Grand Total both shown")
