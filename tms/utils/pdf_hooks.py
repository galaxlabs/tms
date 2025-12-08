import frappe
from frappe.utils.file_manager import save_file
from tms.utils.chrome_pdf import get_pdf as chrome_get_pdf


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

# import frappe
# from frappe import _
# from frappe import publish_progress

# from tms.utils.pdf_engine import generate_pdf, save_pdf


# def create_pdf_on_submit(doc, event=None):
#     """
#     Called from hooks.py for on_submit events.
#     Reads Single Doctype: PDF Settings
#     """

#     settings = frappe.get_single("PDF Settings")

#     # Convert Doctype to fieldname
#     slug = doc.doctype.lower().replace(" ", "_")  # "Sales Invoice" -> "sales_invoice"
#     if not settings.get(slug):
#         return  # PDF generation disabled for this Doctype

#     # Progress for UI (optional)
#     publish_progress(percent=10, title=_("Creating PDF..."))

#     # Optional language override
#     lang = getattr(doc, "language", None)
#     if lang:
#         frappe.local.lang = lang

#     # Determine print format
#     print_format = None
#     if doc.doctype == "Trip":
#         print_format = "Trip"  # your default Trip format
#     else:
#         # default / custom logic for other doctypes
#         print_format = None

#     # 1. Generate PDF (Chrome-based)
#     pdf_bytes = generate_pdf(doc.doctype, doc.name, print_format=print_format)

#     publish_progress(percent=60, title=_("Saving PDF..."))

#     # 2. Folder structure
#     folder = _build_folder_tree(doc)

#     # 3. For Trip → PUBLIC PDF (WhatsApp)
#     make_public = True if doc.doctype == "Trip" else False

#     file_url, file_name, file_id = save_pdf(
#         pdf_bytes,
#         doc.doctype,
#         doc.name,
#         folder=folder,
#         public=make_public,
#     )

#     publish_progress(percent=100, title=_("PDF Created Successfully"))

#     # Optional: store PDF on doc
#     if hasattr(doc, "last_pdf_url"):
#         doc.db_set("last_pdf_url", file_url)
#     if hasattr(doc, "last_pdf_file"):
#         doc.db_set("last_pdf_file", file_id)


# def _build_folder_tree(doc):
#     """Organize PDFs by Doctype / Party."""
#     from frappe.core.doctype.file.file import create_new_folder

#     doctype_folder = f"Home/{doc.doctype}"
#     if not frappe.db.exists("File", doctype_folder):
#         create_new_folder(doc.doctype, "Home")

#     subfolder_name = getattr(doc, "customer", None) or getattr(doc, "party_name", None)
#     if not subfolder_name:
#         subfolder_name = doc.name

#     full_path = f"{doctype_folder}/{subfolder_name}"

#     if not frappe.db.exists("File", full_path):
#         create_new_folder(subfolder_name, doctype_folder)

#     return full_path
