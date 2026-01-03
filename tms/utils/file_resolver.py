# apps/tms/tms/utils/file_resolver.py
from __future__ import annotations

import os
import frappe
from frappe.utils import get_bench_path


def _abs_site_path() -> str:
    """
    Always return absolute site path regardless of process CWD.
    """
    site = getattr(frappe.local, "site", None) or frappe.local.site
    return os.path.join(get_bench_path(), "sites", site)


def file_url_to_path(file_url: str | None) -> str | None:
    if not file_url:
        return None

    url = str(file_url).strip()
    if not url:
        return None

    # Absolute filesystem path already
    if os.path.isabs(url) and os.path.exists(url):
        return url

    site_path = _abs_site_path()

    # /private/files/xxx
    if url.startswith("/private/files/"):
        fname = url.split("/private/files/", 1)[1]
        p = os.path.join(site_path, "private", "files", fname)
        return p if os.path.exists(p) else None

    # /files/xxx
    if url.startswith("/files/"):
        fname = url.split("/files/", 1)[1]
        p = os.path.join(site_path, "public", "files", fname)
        return p if os.path.exists(p) else None

    # Fallback: try File doctype lookup (if someone passed an old/redirected URL)
    file_doc_url = frappe.db.get_value("File", {"file_url": url}, "file_url")
    if file_doc_url and file_doc_url != url:
        return file_url_to_path(file_doc_url)

    return None
