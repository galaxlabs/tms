import frappe
from frappe.utils import today, get_first_day, get_last_day, add_days, formatdate

def auto_generate_rent_invoices():
    today = frappe.utils.today()
    first_day = frappe.utils.get_first_day(today)
    last_day = frappe.utils.get_last_day(today)

    contracts = frappe.get_all("Rental Contract", filters={
        "status": "Active",
        "from_date": ["<=", today],
        "to_date": [">=", today]
    })

    for c in contracts:
        doc = frappe.get_doc("Rental Contract", c.name)

        # Prevent duplicate invoices
        exists = frappe.db.exists("Sales Invoice", {
            "customer": doc.tenant.customer,
            "posting_date": ["between", [first_day, last_day]],
            "docstatus": 1
        })

        if not exists:
            create_monthly_invoice(doc.name)
def create_monthly_invoice(rental_contract_name):
    rental_contract = frappe.get_doc("Rental Contract", rental_contract_name)

    invoice = frappe.get_doc({
        "doctype": "Sales Invoice",
        "customer": rental_contract.tenant.customer,
        "posting_date": frappe.utils.today(),
        "due_date": frappe.utils.add_days(frappe.utils.today(), 30),
        "items": [{
            "item_code": rental_contract.item_code,
            "qty": 1,
            "rate": rental_contract.monthly_rent,
            "amount": rental_contract.monthly_rent
        }],
        "rental_contract": rental_contract.name
    })

    invoice.insert()
    invoice.submit()
    frappe.db.commit()

def create_rent_invoice(contract_name):
    contract = frappe.get_doc("Rental Contract", contract_name)

    if contract.billing_period == "Monthly":
        amount = contract.monthly_rent
    elif contract.billing_period == "Weekly":
        amount = contract.monthly_rent / 4.0
    elif contract.billing_period == "Yearly":
        amount = contract.monthly_rent * 12
    else:
        frappe.throw("Unsupported billing period")

    invoice = frappe.new_doc("Sales Invoice")
    invoice.customer = contract.tenant.customer
    invoice.append("items", {
        "item_code": "RENT",
        "qty": 1,
        "rate": amount,
        "description": f"Rent ({contract.billing_period}) - {frappe.utils.formatdate(frappe.utils.today())}"
    })
    invoice.due_date = frappe.utils.add_days(frappe.utils.today(), 5)
    invoice.insert(ignore_permissions=True)
    invoice.submit()

    return invoice.name
