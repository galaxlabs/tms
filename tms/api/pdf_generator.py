import frappe
import re
from frappe.utils.file_manager import save_file
from tms.utils.pdf_engine import generate_pdf as engine_generate_pdf

PURCHASE_DOCTYPES = {"Purchase Invoice", "Purchase Order", "Supplier Quotation"}


@frappe.whitelist()
def generate_pdf(doctype, docname, print_format):
    doc = frappe.get_doc(doctype, docname)
    party_name, party_type = get_party_info(doc, doctype)
    folder_path = _ensure_folder_path(party_name, party_type)

    pf_clean = clean_name(print_format)
    doc_clean = clean_name(docname)
    filename = f"{doc_clean} {pf_clean}.pdf"

    _cleanup_old_file(folder_path, filename)

    pdf_bytes = engine_generate_pdf(doctype, docname, print_format=print_format)

    file_doc = save_file(
        fname=filename,
        content=pdf_bytes,
        dt=doctype,
        dn=docname,
        folder=folder_path,
        is_private=1,
    )

    root_label = "Suppliers" if party_type == "Supplier" else "Customers"

    return {
        "file_url": file_doc.file_url,
        "file_name": filename,
        "folder": f"{root_label} / {party_name}",
    }


def _cleanup_old_file(folder_path, filename):
    base_name = filename.rsplit(".", 1)[0]
    old_files = frappe.db.get_all(
        "File",
        filters={
            "file_name": ["like", f"{base_name}%.pdf"],
            "folder": folder_path,
            "is_folder": 0,
        },
        pluck="name",
    )
    for name in old_files:
        frappe.delete_doc("File", name, ignore_permissions=True)


def _ensure_folder_path(party_name, party_type):
    home = frappe.get_doc("File", {"file_name": "Home", "is_folder": 1})
    root = "Suppliers" if party_type == "Supplier" else "Customers"
    root_folder = _ensure_folder(root, home.name)
    party_folder = _ensure_folder(clean_name(party_name), root_folder)
    return party_folder


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


def get_party_info(doc, doctype):
    if doctype in PURCHASE_DOCTYPES:
        supplier = doc.get("supplier") or ""
        if supplier and frappe.db.exists("Supplier", supplier):
            s = frappe.get_cached_doc("Supplier", supplier)
            return (s.supplier_name or supplier, "Supplier")
        return (supplier or "Unknown Supplier", "Supplier")

    if doctype == "Trip Invoice":
        passenger_name = doc.get("customer_name_text") or doc.get("invoice_passenger_name") or ""
        if passenger_name:
            return (passenger_name, "Customer")

    customer = doc.get("customer") or doc.get("party_name") or ""
    if customer and frappe.db.exists("Customer", customer):
        c = frappe.get_cached_doc("Customer", customer)
        return (c.get("customer_name_text") or c.customer_name or customer, "Customer")
    return (doc.get("customer_name_text") or doc.get("invoice_passenger_name") or customer or "Unknown Customer", "Customer")


def clean_name(name):
    name = re.sub(r"[^\w\s\-_]", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:80]
