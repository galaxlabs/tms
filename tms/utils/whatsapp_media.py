import frappe
import requests
from frappe.utils.file_manager import save_file


def attach_whatsapp_media_to_trip(wa_doc, trip):
    """
    wa_doc: WhatsApp Message doc from official app.
    trip: Trip doc.

    Adjust field names (media_url/media_id) according to your WA Message DocType.
    """
    media_url = getattr(wa_doc, "media_url", None)
    media_id = getattr(wa_doc, "media_id", None)

    if not (media_url or media_id):
        return None

    # TODO: if official app exposes helper like get_media_content(media_id), use that here

    try:
        # If using raw URL, make sure auth header is set as required.
        resp = requests.get(media_url, timeout=20)
        resp.raise_for_status()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "[TMS WA] Failed to download WA media")
        return None

    filename = f"Trip-{trip.name}-{wa_doc.name}.jpg"

    file_doc = save_file(
        filename=filename,
        content=resp.content,
        dt="Trip",
        dn=trip.name,
        is_private=1,
    )

    return file_doc
