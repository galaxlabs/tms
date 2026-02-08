import secrets
import frappe
from urllib.parse import quote


def set_invoice_public_qr(doc, method=None):
    if not doc.name or doc.name.startswith("new-sales-invoice"):
        return

    BASE_URL = "https://tms.galaxylabs.online"
    PRINT_FORMAT = "Sales Invoice Print"

    if not doc.zatca_qr_png:
        doc.zatca_qr_png = secrets.token_urlsafe(16)

    token = doc.zatca_qr_png
    fmt = quote(PRINT_FORMAT)

    doc.zatca_qr_payload = (
        f"{BASE_URL}/api/method/tms.api.invoice_public.print_invoice"
        f"?name={doc.name}&token={token}&format={fmt}"
    )

@frappe.whitelist(allow_guest=True)
def print_invoice(name, token, format="Sales Invoice Print"):
    doc = frappe.get_doc("Sales Invoice", name)

    # Validate token
    if not doc.zatca_qr_png or doc.zatca_qr_png != token:
        frappe.throw("Invalid or expired link", frappe.PermissionError)

    # Render print HTML
    html = frappe.get_print(
        doctype="Sales Invoice",
        name=name,
        print_format=format,
        no_letterhead=0
    )

    # Convert to PDF
    pdf = get_pdf(html)

    # Return PDF inline (browser opens it)
    frappe.local.response.filename = f"{name}.pdf"
    frappe.local.response.filecontent = pdf
    frappe.local.response.type = "download"
    frappe.local.response.display_content_as = "inline"
    frappe.local.response.content_type = "application/pdf"