import frappe

from tms.utils.zatca_invoice import ensure_public_invoice_qr, render_sales_invoice_pdf


def set_invoice_public_qr(doc, method=None):
    return ensure_public_invoice_qr(
        doc,
        method=method,
        endpoint="tms.api.invoice_public.print_invoice",
    )


@frappe.whitelist()
def print_invoice(name, token=None, format=None):
    pdf = render_sales_invoice_pdf(name, token, print_format=format)
    frappe.local.response.filename = f"{name}.pdf"
    frappe.local.response.filecontent = pdf
    frappe.local.response.type = "download"
    frappe.local.response.display_content_as = "inline"
    frappe.local.response.content_type = "application/pdf"
