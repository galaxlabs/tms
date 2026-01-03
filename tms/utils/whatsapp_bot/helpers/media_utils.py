import frappe

def resolve_file_url(message_doc):
    """Return file_url for this WhatsApp Message from attach field or linked File."""
    if not message_doc:
        return None

    attach = (getattr(message_doc, "attach", "") or "").strip()
    if attach:
        return attach

    # fallback: read from File table
    file_url = frappe.db.get_value(
        "File",
        {"attached_to_doctype": "WhatsApp Message", "attached_to_name": message_doc.name},
        "file_url",
        order_by="creation desc",
    )
    return file_url

# import frappe


# def resolve_file_url(message_doc) -> str:
#     """
#     Get file_url from:
#     1) message_doc.attach
#     2) File record attached to WhatsApp Message
#     """
#     # 1) direct attach field
#     url = (getattr(message_doc, "attach", "") or "").strip()
#     if url:
#         return url

#     # 2) fallback: File table attached to this message
#     f = frappe.db.get_value(
#         "File",
#         {
#             "attached_to_doctype": "WhatsApp Message",
#             "attached_to_name": message_doc.name,
#         },
#         "file_url",
#     )
#     return (f or "").strip()
