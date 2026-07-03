import frappe

OLD_BLOCK = """            <!--<tr><td>Paid Amount</td><td class="num">{{ money(doc.paid_amount or 0) }}</td></tr>-->
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

NEW_BLOCK = """            {% if apply_retention and retention_amount > 0 %}
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

RETENTION_CSS = """
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

def run():
    pf = frappe.get_doc("Print Format", "ZATCA Dynamic")
    html = pf.html
    css = pf.css
    
    # Convert CRLF to LF for matching, convert OLD_BLOCK to CRLF for the actual HTML
    html_lf = html.replace('\r\n', '\n')
    old_lf = OLD_BLOCK.replace('\r\n', '\n')
    new_lf = NEW_BLOCK
    
    if old_lf not in html_lf:
        print("OLD_BLOCK not found!")
        return
    
    html_lf = html_lf.replace(old_lf, new_lf)
    html = html_lf.replace('\n', '\r\n')
    pf.html = html
    
    if ".net-payable-row" not in css:
        idx = css.find("totals-table tr:last-child td {")
        if idx >= 0:
            end = css.find("}", idx)
            if end >= 0:
                css = css[:end+1] + RETENTION_CSS + css[end+1:]
                pf.css = css
    
    pf.save()
    
    # Verify
    pf2 = frappe.get_doc("Print Format", "ZATCA Dynamic")
    print("✅ ZATCA Dynamic retention logic updated")
    print(f"   Net Payable: {'Net Payable After Retention' in pf2.html}")
    print(f"   Grand Total: {'Grand Total' in pf2.html}")
    print(f"   Outstanding (if): {'{% else %}' in pf2.html}")
    print(f"   CSS retention: {'.net-payable-row' in pf2.css}")
