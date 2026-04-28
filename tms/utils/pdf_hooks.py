import frappe
from frappe.utils.file_manager import save_file
from tms.utils.chrome_pdf import get_pdf as chrome_get_pdf
from tms.utils.pdf_engine import generate_pdf, save_pdf
from tms.utils.zatca_invoice import (
    DEFAULT_ZATCA_PDFA_PRINT_FORMAT,
    generate_sales_invoice_pdfa_3b_bytes,
    resolve_sales_invoice_print_format,
)


def create_trip_pdf(doc, event=None):
    """
    Called on Trip after_save.
    Creates PUBLIC PDF ONLY IF one doesn't already exist.
    Uses Chrome PDF + Trip print format.
    """

    # --- Do not regenerate if we already have a public PDF ---
    existing = frappe.get_all(
        "File",
        filters={
            "attached_to_doctype": "Trip",
            "attached_to_name": doc.name,
            "is_private": 0,  # public only
        },
        limit=1,
        fields=["name"]
    )

    if existing:
        return  # Already exists → skip creation


    # --- Render HTML using your Trip print format ---
    html = frappe.get_print(
        "Trip",
        doc.name,
        print_format="Trip",      # YOUR PRINT FORMAT NAME
        no_letterhead=0
    )

    # --- Chrome PDF conversion ---
    pdf_data = chrome_get_pdf(html, options={"page-size": "A4"})

    # --- Save PUBLIC PDF for WhatsApp ---
    fname = f"{doc.name}.pdf".replace(" ", "-").replace("/", "-")

    save_file(
        fname,
        pdf_data,
        "Trip",
        doc.name,
        folder="Home/Trip PDFs",
        is_private=0,  # PUBLIC required for WhatsApp
    )

def create_pdf_on_submit(doc, event=None):
    """Create a PDF attachment for doctypes enabled in PDF Settings."""
    settings = _get_pdf_settings()
    slug = doc.doctype.lower().replace(" ", "_")

    if not settings or not settings.get(slug):
        return

    if doc.doctype == "Trip":
        create_trip_pdf(doc, event=event)
        return

    if _pdf_attachment_exists(doc):
        return

    previous_lang = getattr(frappe.local, "lang", None)

    try:
        lang = getattr(doc, "language", None)
        if lang:
            frappe.local.lang = lang

        if doc.doctype == "Sales Invoice":
            selected_format = resolve_sales_invoice_print_format(doc)
            if selected_format == DEFAULT_ZATCA_PDFA_PRINT_FORMAT:
                pdf_bytes, _, _ = generate_sales_invoice_pdfa_3b_bytes(doc, print_format=selected_format)
            else:
                pdf_bytes = generate_pdf(doc.doctype, doc.name, print_format=selected_format)
        else:
            pdf_bytes = generate_pdf(doc.doctype, doc.name)

        file_url, _, file_id = save_pdf(
            pdf_bytes,
            doc.doctype,
            doc.name,
            folder="Home/Attachments",
            public=False,
        )

        if hasattr(doc, "last_pdf_url"):
            doc.db_set("last_pdf_url", file_url, update_modified=False)
        if hasattr(doc, "last_pdf_file"):
            doc.db_set("last_pdf_file", file_id, update_modified=False)
    finally:
        frappe.local.lang = previous_lang


def _get_pdf_settings():
    if not frappe.db.exists("DocType", "PDF Settings"):
        return None

    return frappe.get_single("PDF Settings")


def _pdf_attachment_exists(doc):
    expected_file_name = f"{doc.doctype}-{doc.name}.pdf".replace(" ", "-").replace("/", "-")
    return bool(
        frappe.get_all(
            "File",
            filters={
                "attached_to_doctype": doc.doctype,
                "attached_to_name": doc.name,
                "file_name": expected_file_name,
            },
            limit=1,
            pluck="name",
        )
    )
