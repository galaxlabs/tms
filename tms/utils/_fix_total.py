import frappe

def run():
    pf = frappe.get_doc('Print Format', 'Profarma Invoice')
    idx = pf.html.find('money(row.amount or 0)')
    if idx < 0:
        print('ERROR: pattern not found')
        return
    
    chunk = pf.html[idx-30:idx+100]
    print('CHUNK:', repr(chunk))
    
    old = '<td class=num>{{ money(row.amount or 0) }}</td>\n          </tr>\n          {% endfor %}'
    new = '{% if has_vat %}\n            <td class=num>{{ money((row.amount or 0) + (row.tax_amount or 0)) }}</td>\n            {% else %}\n            <td class=num>{{ money(row.amount or 0) }}</td>\n            {% endif %}\n          </tr>\n          {% endfor %}'
    
    count = pf.html.count(old)
    if count == 0:
        print('ERROR: old pattern not found')
        return
    
    pf.html = pf.html.replace(old, new)
    pf.save()
    print(f'OK: replaced {count} occurrence(s)')
