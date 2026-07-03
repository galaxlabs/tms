import frappe

RETENTION_HTML = """            {% if apply_retention and retention_amount > 0 %}
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
            {% else %}
              <tr><td>Paid Amount</td><td class="num">{{ money(doc.paid_amount or 0) }}</td></tr>
              <tr><td>Outstanding</td><td class="num">{{ money(doc.outstanding_amount) }}</td></tr>
              <tr><td>Grand Total</td><td class="num">{{ money(doc.grand_total) }}</td></tr>
            {% endif %}"""

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
    
    html_lf = html.replace('\r\n', '\n')
    
    # Current pattern on new VPS (after my previous fix)
    current = """            {% if apply_retention and retention_amount > 0 %}
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
            <tr><td>Grand Total</td><td class="num">{{ money(doc.grand_total) }}</td></tr>""".replace('\r\n', '\n')
    
    if current not in html_lf:
        print("Pattern not found!")
        idx = html_lf.find("retention-row")
        if idx >= 0:
            end = html_lf.find("</table>", idx)
            print(html_lf[idx-100:end if end > 0 else idx + 600])
        return
    
    html_lf = html_lf.replace(current, RETENTION_HTML)
    html = html_lf.replace('\n', '\r\n')
    pf.html = html
    
    # CSS already exists from previous fix, but ensure it's correct
    if ".net-payable-row" not in css:
        idx_css = css.find("totals-table tr:last-child td {")
        if idx_css >= 0:
            end_brace = css.find("}", idx_css)
            css = css[:end_brace+1] + RETENTION_CSS + css[end_brace+1:]
            pf.css = css
    
    pf.save()
    print("✅ ZATCA Dynamic updated")
    print(f"   Net Payable After Retention: {'Net Payable After Retention' in pf.html}")
    has_gt = 'money(doc.grand_total)' in pf.html
    has_else = '{% else %}' in pf.html
    print(f"   Grand Total present: {has_gt} (only in else branch: {has_else})")
    
    # Verify
    pf2 = frappe.get_doc("Print Format", "ZATCA Dynamic")
    html2 = pf2.html
    idx = html2.find("totals-table")
    idx2 = html2.find("bank-table", idx)
    print("\n=== Current totals HTML ===")
    print(html2[idx:idx2 if idx2 > 0 else idx + 1500])
