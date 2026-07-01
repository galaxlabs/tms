import frappe

def run():
    pf = frappe.get_doc("Print Format", "Profarma Invoice")
    html = pf.html
    
    # Find retention display in totals
    idx = html.find("net_payable_after_retention")
    if idx >= 0:
        start = html.rfind("<tr", 0, idx)
        if start < 0:
            start = max(0, idx - 200)
        # Find the next </table> after the retention code
        table_end = html.find("</table>", html.find("Total Amounts", idx))
        if table_end >= 0:
            table_end += len("</table>")
        else:
            table_end = min(len(html), idx + 600)
        print(html[start:table_end])
    else:
        print("net_payable_after_retention not found in Profarma")
        
        # Search for "Retention" in totals area
        r_idx = html.find("Retention")
        if r_idx >= 0:
            print(f"\n'Retention' found at {r_idx}")
            print(html[max(0,r_idx-300):min(len(html), r_idx+400)])
