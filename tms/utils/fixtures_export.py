import frappe
from frappe.utils.fixtures import export_fixtures

@frappe.whitelist()
def run():
    """
    Export fixtures according to hooks.py (with your filters).
    Equivalent to: bench --site <site> export-fixtures
    """
    export_fixtures()
    return "OK: fixtures exported"