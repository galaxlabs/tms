import frappe
import re
from frappe.utils.file_manager import save_file
from tms.utils.pdf_engine import generate_pdf as engine_generate_pdf


@frappe.whitelist()
def generate_pdf(doctype, docname, print_format):
    """Generate PDF with customer-based folder structure"""
    doc = frappe.get_doc(doctype, docname)

    customer_name = get_customer_name(doc)
    folder_type = get_subfolder(doctype)

    # Create folder hierarchy
    folder_path = _ensure_folder_path(customer_name, folder_type)

    pf_clean = clean_name(print_format)
    doc_clean = clean_name(docname)
    cust_clean = clean_name(customer_name)
    filename = f"{cust_clean} {pf_clean} {doc_clean}.pdf"

    pdf_bytes = engine_generate_pdf(doctype, docname, print_format=print_format)

    file_doc = save_file(
        fname=filename,
        content=pdf_bytes,
        dt=doctype,
        dn=docname,
        folder=folder_path,
        is_private=1,
    )

    return {
        "file_url": file_doc.file_url,
        "file_name": filename,
        "folder": f"{customer_name} / {folder_type}",
    }


def _ensure_folder_path(customer_name, subfolder=None):
    """Create folder hierarchy Home/Customers/{customer}/{subfolder}"""
    home = frappe.get_doc("File", {"file_name": "Home", "is_folder": 1})

    # Create Customers root
    cust_root = _ensure_folder("Customers", home.name)
    # Create customer folder
    cust_folder = _ensure_folder(clean_name(customer_name), cust_root)

    if subfolder:
        return _ensure_folder(clean_name(subfolder), cust_folder)

    return cust_folder


def _ensure_folder(folder_name, parent_folder):
    existing = frappe.db.get_value(
        "File",
        {"file_name": folder_name, "folder": parent_folder, "is_folder": 1},
    )
    if existing:
        return existing

    folder = frappe.get_doc({
        "doctype": "File",
        "file_name": folder_name,
        "is_folder": 1,
        "folder": parent_folder,
    })
    folder.insert(ignore_permissions=True)
    return folder.name


def get_customer_name(doc):
    customer_field = doc.get("customer") or doc.get("party_name") or ""
    if not customer_field:
        return "Unknown"
    for dn in ["Customer", "Supplier"]:
        if frappe.db.exists(dn, customer_field):
            c = frappe.get_cached_doc(dn, customer_field)
            return c.customer_name or c.supplier_name or customer_field
    return customer_field


def get_subfolder(doctype):
    return {
        "Quotation": "Quotation",
        "Sales Invoice": "Sales Invoice",
        "Sales Order": "Sales Order",
        "Delivery Note": "Delivery Note",
        "Purchase Invoice": "Purchase Invoice",
        "Purchase Order": "Purchase Order",
        "Supplier Quotation": "Supplier Quotation",
        "Payment Entry": "Payment Entry",
    }.get(doctype, "Other")


def clean_name(name):
    name = re.sub(r"[^\w\s\-_]", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:80]
