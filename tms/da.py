import frappe

def run():
    pf = frappe.get_doc("Print Format", "Celtco Quotation - No VAT")
    html = pf.html
    
    # Find money macro and its surrounding context
    idx = html.find("{% macro money")
    if idx >= 0:
        end = html.find("{%- endmacro %}", idx) + len("{%- endmacro %}")
        print("=== MONEY MACRO ===")
        print(repr(html[idx-100:end+100]))
    else:
        print("MONEY MACRO MISSING!")
    
    # Find first call to money()
    idx2 = html.find("{{ money(")
    if idx2 >= 0:
        print("\n=== FIRST MONEY CALL ===")
        print(repr(html[max(0,idx2-50):idx2+80]))
        
    # Check if macro is inside any {% if %} or other scope
    # Find all {% between macro start and template start
    before_macro = html[:idx]
    open_blocks = before_macro.count("{% ") + before_macro.count("{%-") + before_macro.count("{%+")
    close_blocks = before_macro.count("%} ") + before_macro.count("-%}") + before_macro.count("+%}")
    print(f"\nBlocks before macro: open={open_blocks}, close={close_blocks}")
    
    # Check specific block types that haven't been closed
    for tag in ["if", "for", "block", "macro"]:
        opens = before_macro.count(f"{{% {tag}") + before_macro.count(f"{{%- {tag}") 
        closes = before_macro.count(f"{{% end{tag}") + before_macro.count(f"{{%- end{tag}")
        if opens != closes:
            print(f"  UNCLOSED '{tag}': open={opens}, close={closes}")
