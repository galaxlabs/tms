import frappe

def run():
    pf = frappe.get_doc("Print Format", "ZATCA Dynamic")
    html = pf.html
    
    # Find the totals section - look for the retention display
    idx = html.find("Retention")
    if idx >= 0:
        print("=== ZATCA RETENTION DISPLAY CODE ===")
        # Print from a bit before to capture the full totals section
        start = html.rfind("<tr class=", 0, idx)
        if start < 0:
            start = max(0, idx - 200)
        end = html.find("</table>", idx)
        if end >= 0:
            end = end + len("</table>")
        else:
            end = min(len(html), idx + 800)
        print(html[start:end])
    
    # Now let's also check the end of the HTML to see the footer
    print("\n=== LAST 500 CHARS ===")
    print(html[-500:])
