import frappe

def run():
    pf = frappe.get_doc('Print Format', 'Profarma Invoice')
    
    old = '            <td class="num">{{ money(row.amount or 0) }}</td>\n          </tr>\n          {% endfor %}'
    new = '            {% if has_vat %}\n            <td class="num">{{ money((row.amount or 0) + (row.tax_amount or 0)) }}</td>\n            {% else %}\n            <td class="num">{{ money(row.amount or 0) }}</td>\n            {% endif %}\n          </tr>\n          {% endfor %}'
    
    count = pf.html.count(old)
    print(f'Pattern found: {count}')
    if count > 0:
        pf.html = pf.html.replace(old, new)
        pf.save()
        print('Saved!')
    else:
        # Debug raw view
        idx = pf.html.find('money(row.amount or 0)')
        print(repr(pf.html[idx-50:idx+100]))
