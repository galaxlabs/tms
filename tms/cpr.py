import frappe

def run():
    pf = frappe.get_doc("Print Format", "Profarma Invoice")
    html = pf.html
    
    # Find retention in totals display
    idx = html.find("net_payable_after_retention")
    if idx >= 0:
        # Print from 500 before to 500 after
        start = max(0, html.rfind("<tr", 0, idx))
        if start < 0:
            start = max(0, idx - 400)
        end = html.find("</table>", idx)
        if end >= 0:
            end += len("</table>")
        else:
            end = min(len(html), idx + 500)
        print(html[start:end])

    # Check if retention display exists in Profarma totals
    print("\n\n=== SEARCH FOR RETENTION IN TOTALS ===")
    totals_idx = html.find("{% if not show_single_line")
    if totals_idx < 0:
        totals_idx = html.find("Total")
    if totals_idx >= 0:
        print(html[totals_idx:min(len(html), totals_idx+2500)])
