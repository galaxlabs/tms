import secrets
import frappe

def set_public_invoice_qr(doc, method=None):
    base_url = "https://tms.galaxylabs.online"
    print_format = "Sales Invoice Print"

    # token storage reuse: zatca_qr_png
    if not doc.zatca_qr_png:
        doc.zatca_qr_png = secrets.token_urlsafe(16)

    key = doc.zatca_qr_png

    # public URL (served by our own whitelisted method below)
    doc.zatca_qr_payload = (
        f"{base_url}/api/method/tms.api.invoice_qr.public_print?"
        f"name={doc.name}&key={key}&format={print_format}"
    )


@frappe.whitelist(allow_guest=True)
def public_print(name, key, format="Sales Invoice Print"):
    # fetch invoice
    doc = frappe.get_doc("Sales Invoice", name)

    # validate token
    if not doc.zatca_qr_png or doc.zatca_qr_png != key:
        frappe.throw("Invalid link", frappe.PermissionError)

    # render print (HTML)
    html = frappe.get_print("Sales Invoice", name, print_format=format)

    return html

@frappe.whitelist(allow_guest=True)
def print_invoice(name, token, format="Sales Invoice Print"):
    """
    Public printable invoice endpoint
    QR opens THIS
    """

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

    return html
