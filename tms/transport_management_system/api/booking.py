import frappe

@frappe.whitelist(allow_guest=True)
def create_booking(**kwargs):
    required_key = frappe.get_site_config().get("transport_hub_api_key")
    sent_key = (
        frappe.get_request_header("X-TransportHub-Key")
        or frappe.form_dict.get("api_key")
    )

    if required_key and sent_key != required_key:
        frappe.throw("Unauthorized", frappe.PermissionError)

    data = frappe._dict(kwargs)

    doc = frappe.get_doc({
        "doctype": "Booking",
        "customer_name": data.get("customer_name"),
        "phone": data.get("phone"),
        "email": data.get("email"),
        "pickup_location": data.get("pickup_location"),
        "dropoff_location": data.get("dropoff_location"),
        "travel_date": data.get("travel_date"),
        "vehicle_type": data.get("vehicle_type"),
        "passengers": data.get("passengers") or 0,
        "message": data.get("message"),
        "source": data.get("source") or "Website",
        "status": "New",
    })

    doc.insert(ignore_permissions=True)

    # WhatsApp sending should NOT be here if you're doing it in Booking.after_insert()
    return {"name": doc.name}

# import frappe

# @frappe.whitelist(allow_guest=True)
# def create_booking(**kwargs):
#     data = frappe._dict(kwargs)

#     doc = frappe.get_doc({
#         "doctype": "Booking",
#         "customer_name": data.get("customer_name"),
#         "phone": data.get("phone"),
#         "email": data.get("email"),
#         "pickup_location": data.get("pickup_location"),
#         "dropoff_location": data.get("dropoff_location"),
#         "travel_date": data.get("travel_date"),
#         "vehicle_type": data.get("vehicle_type"),
#         "passengers": data.get("passengers") or 0,
#         "message": data.get("message"),
#         "source": data.get("source") or "Transport Hub",
#         "status": "New"
#     })

#     doc.insert(ignore_permissions=True)

#     # Try WhatsApp, but DO NOT fail booking if WhatsApp fails
#     whatsapp_ok = False
#     whatsapp_error = None

#     try:
#         # Send to your admin number (digits only)
#         admin_number = "966572405550"

#         # IMPORTANT: if your WhatsApp system requires templates for outbound,
#         # this may still fail unless you send a template instead of text.
#         frappe.get_doc({
#             "doctype": "WhatsApp Message",
#             "type": "Outgoing",
#             "message_type": "Manual",
#             "to": admin_number,
#             "content_type": "text",
#             "message": (
#                 f"🚌 New Booking: {doc.name}\n"
#                 f"Name: {doc.customer_name}\n"
#                 f"Phone: {doc.phone}\n"
#                 f"Email: {doc.email or '-'}\n"
#                 f"Message: {doc.message or '-'}\n"
#                 f"Source: {doc.source or '-'}"
#             ),
#             "reference_doctype": "Booking",
#             "reference_name": doc.name
#         }).insert(ignore_permissions=True)

#         whatsapp_ok = True
#         doc.db_set("whatsapp_sent", 1)

#     except Exception as e:
#         whatsapp_error = str(e)
#         frappe.log_error(frappe.get_traceback(), "WhatsApp Send Failed (Booking)")

#     return {
#         "name": doc.name,
#         "whatsapp_ok": whatsapp_ok,
#         "whatsapp_error": whatsapp_error
#     }
# import frappe

# @frappe.whitelist(allow_guest=True)
# def create_booking(**kwargs):
#     data = frappe._dict(kwargs)

#     doc = frappe.get_doc({
#         "doctype": "Booking",
#         "customer_name": data.get("customer_name"),
#         "phone": data.get("phone"),
#         "email": data.get("email"),
#         "pickup_location": data.get("pickup_location"),
#         "dropoff_location": data.get("dropoff_location"),
#         "travel_date": data.get("travel_date"),
#         "vehicle_type": data.get("vehicle_type"),
#         "passengers": data.get("passengers") or 0,
#         "message": data.get("message"),
#         "source": data.get("source") or "Transport Hub",
#         "status": "New"
#     })

#     doc.insert(ignore_permissions=True)

#     # Try WhatsApp, but DO NOT fail booking if WhatsApp fails
#     whatsapp_ok = False
#     whatsapp_error = None

#     try:
#         # Send to your admin number (digits only)
#         admin_number = "966572405550"

#         # IMPORTANT: if your WhatsApp system requires templates for outbound,
#         # this may still fail unless you send a template instead of text.
#         frappe.get_doc({
#             "doctype": "WhatsApp Message",
#             "type": "Outgoing",
#             "message_type": "Manual",
#             "to": admin_number,
#             "content_type": "text",
#             "message": (
#                 f"🚌 New Booking: {doc.name}\n"
#                 f"Name: {doc.customer_name}\n"
#                 f"Phone: {doc.phone}\n"
#                 f"Email: {doc.email or '-'}\n"
#                 f"Message: {doc.message or '-'}\n"
#                 f"Source: {doc.source or '-'}"
#             ),
#             "reference_doctype": "Booking",
#             "reference_name": doc.name
#         }).insert(ignore_permissions=True)

#         whatsapp_ok = True
#         doc.db_set("whatsapp_sent", 1)

#     except Exception as e:
#         whatsapp_error = str(e)
#         frappe.log_error(frappe.get_traceback(), "WhatsApp Send Failed (Booking)")

#     return {
#         "name": doc.name,
#         "whatsapp_ok": whatsapp_ok,
#         "whatsapp_error": whatsapp_error
#     }
# import frappe

# @frappe.whitelist(allow_guest=True)
# def create_booking(**kwargs):
#     data = frappe._dict(kwargs)

#     doc = frappe.get_doc({
#         "doctype": "Booking",
#         "customer_name": data.get("customer_name"),
#         "phone": data.get("phone"),
#         "email": data.get("email"),
#         "pickup_location": data.get("pickup_location"),
#         "dropoff_location": data.get("dropoff_location"),
#         "travel_date": data.get("travel_date"),
#         "vehicle_type": data.get("vehicle_type"),
#         "passengers": data.get("passengers") or 0,
#         "message": data.get("message"),
#         "source": data.get("source") or "Transport Hub",
#         "status": "New"
#     })

#     doc.insert(ignore_permissions=True)

#     # Try WhatsApp, but DO NOT fail booking if WhatsApp fails
#     whatsapp_ok = False
#     whatsapp_error = None

#     try:
#         # Send to your admin number (digits only)
#         admin_number = "966572405550"

#         # IMPORTANT: if your WhatsApp system requires templates for outbound,
#         # this may still fail unless you send a template instead of text.
#         frappe.get_doc({
#             "doctype": "WhatsApp Message",
#             "type": "Outgoing",
#             "message_type": "Manual",
#             "to": admin_number,
#             "content_type": "text",
#             "message": (
#                 f"🚌 New Booking: {doc.name}\n"
#                 f"Name: {doc.customer_name}\n"
#                 f"Phone: {doc.phone}\n"
#                 f"Email: {doc.email or '-'}\n"
#                 f"Message: {doc.message or '-'}\n"
#                 f"Source: {doc.source or '-'}"
#             ),
#             "reference_doctype": "Booking",
#             "reference_name": doc.name
#         }).insert(ignore_permissions=True)

#         whatsapp_ok = True
#         doc.db_set("whatsapp_sent", 1)

#     except Exception as e:
#         whatsapp_error = str(e)
#         frappe.log_error(frappe.get_traceback(), "WhatsApp Send Failed (Booking)")

#     return {
#         "name": doc.name,
#         "whatsapp_ok": whatsapp_ok,
#         "whatsapp_error": whatsapp_error
#     }
