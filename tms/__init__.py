# /home/dg/dg-b/apps/tms/tms/__init__.py
__version__ = "0.0.1"

def override_frappe_get_pdf(bootinfo=None):
    import frappe
    import frappe.utils.pdf as frappe_pdf

    # Avoid running during install/build where site/db may not be ready
    if not getattr(frappe.local, "site", None):
        return
    if getattr(frappe.flags, "in_install", False) or getattr(frappe.flags, "in_migrate", False):
        return

    try:
        from tms.utils.chrome_pdf import get_pdf as chrome_get_pdf
        frappe_pdf.get_pdf = chrome_get_pdf
        frappe.logger().info("tms: Overridden frappe.utils.pdf.get_pdf with Chrome-based generator")
    except Exception:
        # IMPORTANT: do NOT write to DB here
        frappe.logger().exception("tms: Failed to override frappe.utils.pdf.get_pdf")
