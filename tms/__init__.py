__version__ = "0.0.1"

try:
    import frappe
    import frappe.utils.pdf as frappe_pdf
    from tms.utils.chrome_pdf import get_pdf as chrome_get_pdf

    frappe_pdf.get_pdf = chrome_get_pdf
    frappe.logger().info("tms: Overridden frappe.utils.pdf.get_pdf with Chrome-based generator")
except Exception:
    # Do not crash app if something goes wrong
    import frappe
    frappe.log_error(frappe.get_traceback(), "tms: Failed to override frappe.utils.pdf.get_pdf")