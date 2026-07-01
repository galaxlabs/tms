import frappe

def run():
    pf = frappe.get_doc("Print Format", "Celtco Quotation - No VAT")
    html = pf.html
    css = pf.css
    
    # =====================================================================
    # PART 1: Fix HTML - add back quotation-shell, fix money macro position
    # =====================================================================
    
    # The current html starts with <div class="sheet"> - add the wrapper back
    current_start = '<div class="sheet">'
    if html.startswith(current_start):
        html = '<div class="quotation-shell">\n  ' + html
        print("Added quotation-shell wrapper back")
    
    # The html currently ends with </div> - close quotation-shell too
    if html.rstrip().endswith('</div>'):
        # Find the last </div> - it closes sheet, we need to close shell too
        html = html.rstrip() + '\n</div>'
        print("Added closing quotation-shell div")
    
    # =====================================================================
    # PART 2: Move money macro + add total_ns before the HTML content
    # =====================================================================
    
    # Remove the misplaced money macro from its current location
    old_macro = '{% macro money(value) -%}\n  {%- set amount = frappe.utils.flt(value or 0, 2) -%}\n  {{ "{:,.2f}".format(amount).replace(".00", "") }}\n{%- endmacro %}\n\n\n    <table class="totals-grid">'
    new_replacement = '{% macro money(value) -%}\n  {%- set amount = frappe.utils.flt(value or 0, 2) -%}\n  {{ "{:,.2f}".format(amount).replace(".00", "") }}\n{%- endmacro %}\n\n{# Totals #}\n{% set total_ns = namespace(grand=0) %}\n\n{% for row in doc.items or [] %}\n  {% set total_ns.grand = total_ns.grand + frappe.utils.flt(row.amount or 0, 2) %}\n{% endfor %}\n\n    <table class="totals-grid">'
    
    if old_macro in html:
        html = html.replace(old_macro, new_replacement, 1)
        print("Reorganized macro + added total_ns in correct position")
    else:
        print("Old macro pattern not found for replacement")
        idx = html.find("{% macro money")
        if idx >= 0:
            print("Money macro at", idx)
            print(repr(html[idx:idx+150]))
    
    # Check if money macro exists BEFORE the first call
    first_call = html.find("{{ money(")
    macro_def = html.find("{% macro money")
    
    if macro_def >= 0 and first_call >= 0:
        if macro_def > first_call:
            print(f"WARNING: money macro ({macro_def}) is AFTER first call ({first_call})!")
            # Move the macro to right before the items table
            items_start = html.find('<table class="items-table')
            if items_start >= 0:
                macro_end = html.find("{%- endmacro %}", macro_def) + len("{%- endmacro %}")
                macro_block = html[macro_def:macro_end+1]  # include the newline
                # Remove from current position
                html = html[:macro_def] + html[macro_end+1:]
                # Insert before items table
                html = html[:items_start] + macro_block + '\n' + html[items_start:]
                print(f"Moved macro before items table at {items_start}")
        else:
            print("OK: money macro is before first call")
    else:
        if macro_def < 0:
            print("ERROR: money macro not found!")
        if first_call < 0:
            print("ERROR: no calls to money() found!")
    
    # =====================================================================
    # PART 3: Fix CSS
    # =====================================================================
    
    # @page margin
    css = css.replace("margin: 5mm 6mm 12mm 6mm;", "margin: 5mm 6mm 22mm 6mm;")
    
    # Footer position fixed
    css = css.replace(
        ".footer-bar {\n\n  display: table;",
        ".footer-bar {\n  position: fixed !important;\n  left: 0 !important;\n  right: 0 !important;\n  bottom: 0 !important;\n  z-index: 100 !important;\n\n  display: table;"
    )
    
    # Remove page-break, margin-top from footer
    css = css.replace("  margin-top: 0;\n", "")
    css = css.replace("  margin-top: 8mm;\n", "")
    
    # Remove footer-page-break CSS
    old_break = '.footer-page-break {\n  page-break-before: auto;\n  break-before: auto;\n  height: 8mm;\n  display: block;\n}'
    css = css.replace(old_break, "")
    
    # Remove footer-page-break div from HTML
    html = html.replace(
        '\n    <div class="footer-page-break"></div>\n\n    <div class="footer-bar">',
        '\n    <div class="footer-bar">'
    )
    
    # Swap pdf_generator
    pf.pdf_generator = ""
    
    pf.html = html
    pf.css = css
    pf.save()
    print("\nSaved! All fixes applied.")
    
    # Verify
    new_call = pf.html.find("{{ money(")
    new_macro = pf.html.find("{% macro money")
    print(f"First call at: {new_call}, Macro at: {new_macro}")
    print(f"Macro before call: {new_macro < new_call}")
    print(f"total_ns defs: {pf.html.count('set total_ns')}")
    print(f"quotation-shell in html: {'quotation-shell' in pf.html}")
