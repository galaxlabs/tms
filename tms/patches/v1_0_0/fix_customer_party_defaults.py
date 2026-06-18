import frappe

from tms.utils.party_defaults import ensure_customer_party_defaults


def execute():
    if not frappe.db.exists("DocType", "Customer"):
        return

    ensure_customer_party_defaults()
