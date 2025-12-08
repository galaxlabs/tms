import frappe
from frappe.utils.file_manager import save_file
from tms.utils.chrome_pdf import get_pdf as chrome_get_pdf


def generate_pdf(doctype, name, print_format=None):
    """Render HTML → PDF using Chrome engine."""
    html = frappe.get_print(
        doctype,
        name,
        print_format=print_format,
        no_letterhead=0,
    )

    pdf_bytes = chrome_get_pdf(html, options={"page-size": "A4"})
    return pdf_bytes


def save_pdf(
    pdf_bytes,
    doctype,
    name,
    folder="Home/Attachments",
    public=False
):
    """Save PDF and return (file_url, file_name)."""

    fname = f"{doctype}-{name}.pdf".replace(" ", "-").replace("/", "-")

    file_doc = save_file(
        fname=fname,
        content=pdf_bytes,
        dt=doctype,
        dn=name,
        folder=folder,
        is_private=0 if public else 1,
    )

    return (file_doc.file_url, file_doc.file_name, file_doc.name)
