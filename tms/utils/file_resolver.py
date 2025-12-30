# tms/utils/file_resolver.py
import frappe
import os

def file_url_to_path(file_url: str) -> str | None:
    """
    Works for Frappe File URLs like:
      /private/files/xxx.jpg
      /files/xxx.jpg
    Also works if file_url is actually File.name (less common).
    """
    if not file_url:
        return None

    # If a File doc exists with this file_url
    f = frappe.db.get_value("File", {"file_url": file_url}, ["name", "file_url", "is_private"], as_dict=True)
    if not f:
        # maybe file_url is the File name
        if frappe.db.exists("File", file_url):
            f = frappe.get_doc("File", file_url)
            file_url = f.file_url
        else:
            return None

    site_path = frappe.get_site_path()
    # file_url starts with /private/files/... or /files/...
    rel = (file_url or "").lstrip("/")
    abs_path = os.path.join(site_path, rel)
    return abs_path if os.path.exists(abs_path) else None
