import frappe

def run():
    pf = frappe.get_doc('Print Format', 'Profarma Invoice')
    idx = pf.html.find('money(row.amount or 0)')
    # Get the exact indentation from the chunk
    chunk = pf.html[idx-40:idx+150]
    lines = chunk.split('\n')
    print('LINES:')
    for i, line in enumerate(lines):
        print(f'  {i}: {repr(line)}')
