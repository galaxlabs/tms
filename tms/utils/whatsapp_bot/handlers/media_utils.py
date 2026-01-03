import frappe


def resolve_file_url(message_doc) -> str:
    # 1) direct attach field
    url = (getattr(message_doc, "attach", "") or "").strip()
    if url:
        return url

    # 2) File attached to WhatsApp Message by doc.name
    url = frappe.db.get_value(
        "File",
        {"attached_to_doctype": "WhatsApp Message", "attached_to_name": message_doc.name},
        "file_url",
        order_by="creation desc"
    )
    if url:
        return (url or "").strip()

    # 3) File attached by message_id (some implementations do this)
    mid = getattr(message_doc, "message_id", None)
    if mid:
        url = frappe.db.get_value(
            "File",
            {"attached_to_doctype": "WhatsApp Message", "attached_to_name": mid},
            "file_url",
            order_by="creation desc"
        )
        if url:
            return (url or "").strip()

    # 4) File attached to reference_doctype/reference_name (if your webhook uses these)
    ref_doctype = getattr(message_doc, "reference_doctype", None)
    ref_name = getattr(message_doc, "reference_name", None)
    if ref_doctype and ref_name:
        url = frappe.db.get_value(
            "File",
            {"attached_to_doctype": ref_doctype, "attached_to_name": ref_name},
            "file_url",
            order_by="creation desc"
        )
        if url:
            return (url or "").strip()

    return ""


# import frappe

# def resolve_file_url(message_doc):
#     # 1) primary field
#     url = (getattr(message_doc, "attach", "") or "").strip()
#     if url:
#         return url

#     # 2) look for File record attached to this message
#     f = frappe.db.get_value(
#         "File",
#         {
#             "attached_to_doctype": "WhatsApp Message",
#             "attached_to_name": message_doc.name
#         },
#         ["file_url", "file_name"],
#         as_dict=True
#     )
#     if f and f.get("file_url"):
#         return f["file_url"]

#     # 3) sometimes body_param/template_header_parameters can contain something (rare)
#     return ""
