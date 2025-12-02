import json
import frappe
from frappe.utils import now_datetime

from tms.utils.whatsapp_utils import (
    normalize_phone,
    get_or_create_contact,
    send_trip_pdf_via_whatsapp,
)


# ---------------------------------------------------------------------------
# Entry point: after_insert on WhatsApp Message
# ---------------------------------------------------------------------------

def handle_incoming_whatsapp(doc, event=None):
    """
    Hook: called on after_insert of WhatsApp Message.

    Configure in hooks.py:
        "WhatsApp Message": {
            "after_insert": "tms.utils.whatsapp_bot.handle_incoming_whatsapp",
        },
    """
    # only care about Incoming
    if doc.type != "Incoming":
        return

    try:
        content_type = (doc.content_type or "").lower()

        # sender info
        sender_no = normalize_phone(
            getattr(doc, "from_", "") or getattr(doc, "from", "") or ""
        )
        profile_name = (doc.profile_name or "").strip()

        # ensure contact row exists
        contact = get_or_create_contact(sender_no, profile_name)

        if content_type == "text":
            _handle_text_message(doc, contact)
        elif content_type in ("image", "document"):
            _handle_media_message(doc, contact)
        else:
            # ignore reactions, buttons, etc for now
            return

    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            "WhatsApp Bot Error in handle_incoming_whatsapp",
        )


# ---------------------------------------------------------------------------
# Contact helpers
# ---------------------------------------------------------------------------

def _update_contact_state(contact, **kwargs):
    """Update WhatsApp Contacts fields safely."""
    if not contact:
        return

    dirty = False
    for field, value in kwargs.items():
        # only set fields that actually exist on DocType
        if hasattr(contact, field):
            setattr(contact, field, value)
            dirty = True

    if dirty:
        contact.save(ignore_permissions=True)


# ---------------------------------------------------------------------------
# Text handler (passenger count)
# ---------------------------------------------------------------------------

def _handle_text_message(doc, contact):
    """Handle incoming text based on contact.bot_state."""
    if not contact:
        return

    state = (getattr(contact, "bot_state", "") or "").upper()
    text = (doc.message or "").strip()

    # Only one state for now: expecting passenger count
    if state == "ASKED_PASSENGERS":
        num = _extract_int(text)
        if not num or num <= 0:
            msg = (
                "Please send only the number of passengers.\n"
                "من فضلك أرسل عدد الركاب كرقم فقط.\n"
                "براہ کرم صرف مسافروں کی تعداد نمبر میں بھیجیں۔"
            )
            _send_thread_reply(doc, msg)
            return

        # Set expected_passengers & move to COLLECTING_DOCS
        received = int(getattr(contact, "received_images", 0) or 0)
        _update_contact_state(
            contact,
            expected_passengers=num,
            bot_state="COLLECTING_DOCS",
        )

        # If already received some docs, inform status
        remaining = max(num - received, 0)

        if received == 0:
            msg = (
                f"✅ Got it. You said {num} passengers.\n"
                f"Please send {num} clear images or PDFs (Iqama / Passport / Visa / Nusuk), "
                f"one document per passenger.\n\n"
                f"✅ تم التأكيد. عدد الركاب {num}.\n"
                f"من فضلك أرسل {num} صورًا أو ملفات PDF واضحة (إقامة / جواز سفر / تأشيرة / نسك)، "
                f"لكل راكب مستند واحد.\n\n"
                f"✅ ٹھیک ہے، آپ نے {num} مسافروں کا بتایا ہے۔\n"
                f"براہ کرم {num} صاف تصویریں یا پی ڈی ایف بھیجیں (اقامہ / پاسپورٹ / ویزا / نسک)، "
                f"ہر مسافر کے لیے ایک دستاویز۔"
            )
        elif remaining > 0:
            msg = (
                f"✅ I registered {num} passengers.\n"
                f"I already received {received} document(s). "
                f"Please send remaining {remaining} document(s).\n\n"
                f"✅ تم تسجيل {num} ركاب.\n"
                f"تم استلام {received} مستند(ات) حتى الآن. "
                f"من فضلك أرسل باقي {remaining} مستند(ات).\n\n"
                f"✅ {num} مسافروں کا اندراج ہوگیا ہے۔\n"
                f"اب تک {received} دستاویزات موصول ہو چکی ہیں۔ "
                f"براہ کرم باقی {remaining} دستاویز بھیجیں۔"
            )
        else:
            # already have enough docs → finalize immediately
            sender_no = contact.whatsapp_id
            driver_name = _find_driver_by_phone(sender_no)
            if not driver_name:
                # safety: if cannot find driver here, just stop
                _send_thread_reply(
                    doc,
                    "⚠️ System could not verify driver for this number.\n"
                    "⚠️ تعذر على النظام التحقق من السائق لهذا الرقم.\n"
                    "⚠️ سسٹم اس نمبر کے لیے ڈرائیور کی تصدیق نہیں کر سکا۔"
                )
                return

            trip = _get_or_create_trip_for_contact(driver_name, contact)
            _finalize_trip_and_kashf(contact, driver_name, trip)
            return

        _send_thread_reply(doc, msg)

    # other states ignored for now
    return


def _extract_int(text: str):
    """Extract first integer from text."""
    digits = ""
    for ch in text:
        if ch.isdigit():
            digits += ch
        elif digits:
            break
    if not digits:
        return None
    try:
        return int(digits)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Media handler (image / doc)
# ---------------------------------------------------------------------------

def _handle_media_message(doc, contact):
    """Handle incoming image or PDF (WABA Document)."""
    if not contact:
        return

    sender_no = normalize_phone(
        getattr(doc, "from_", "") or getattr(doc, "from", "") or ""
    )
    if not sender_no:
        return

    # 1) Resolve driver (Staff via phone + must have Driver record)
    driver_name = _find_driver_by_phone(sender_no)
    if not driver_name:
        _send_thread_reply(
            doc,
            "⚠️ Your number is not registered as a driver in the system.\n"
            "⚠️ رقمك غير مسجل كسائق في النظام.\n"
            "⚠️ آپ کا نمبر سسٹم میں ڈرائیور کے طور پر رجسٹر نہیں ہے۔"
        )
        return

    # 2) Get or create Trip bound to this contact
    trip = _get_or_create_trip_for_contact(driver_name, contact)

    # 3) Get file_url from WhatsApp Message.attach (created by webhook)
    file_url = (doc.attach or "").strip()
    if not file_url:
        _send_thread_reply(
            doc,
            "🕐 I received your message, but no document/image was attached.\n"
            "🕐 تم استلام رسالتك، لكن لا يوجد مستند أو صورة مرفقة.\n"
            "🕐 میسج ملا لیکن کوئی تصویر یا دستاویز منسلک نہیں تھی۔"
        )
        return

    # 4) Run OCR + create OCR History record
    ocr_ok = _create_ocr_history_and_run_ocr(doc, trip, file_url)

    if not ocr_ok:
        # do NOT increment received_images, ask to resend this image
        msg = (
            "⚠️ This document image is not clear, please send a new clearer image.\n"
            "⚠️ صورة هذا المستند غير واضحة، من فضلك أرسل صورة أوضح.\n"
            "⚠️ اس دستاویز کی تصویر واضح نہیں ہے، براہ کرم نئی صاف تصویر بھیجیں۔"
        )
        _send_thread_reply(doc, msg)
        return

    # 5) Increment received_images
    received = int(getattr(contact, "received_images", 0) or 0) + 1
    expected = int(getattr(contact, "expected_passengers", 0) or 0)

    # If we never asked passenger count yet, ask now (but keep received counter)
    if expected <= 0 and (getattr(contact, "bot_state", "") or "").upper() not in (
        "ASKED_PASSENGERS",
        "COLLECTING_DOCS",
    ):
        _update_contact_state(
            contact, received_images=received, bot_state="ASKED_PASSENGERS"
        )

        msg = (
            "🧾 I received your document.\n"
            "How many passengers are going on this trip?\n\n"
            "🧾 تم استلام مستندك.\n"
            "كم عدد الركاب في هذه الرحلة؟\n\n"
            "🧾 آپ کی دستاویز موصول ہوگئی ہے۔\n"
            "اس سفر پر کتنے مسافر جائیں گے؟"
        )
        _send_thread_reply(doc, msg)
        return

    # If expected already known, update state and inform
    _update_contact_state(
        contact, received_images=received, bot_state="COLLECTING_DOCS"
    )

    if expected > 0:
        if received < expected:
            msg = (
                f"✅ Document {received}/{expected} received.\n"
                f"Please send the remaining {expected - received} document(s).\n\n"
                f"✅ تم استلام المستند رقم {received} من {expected}.\n"
                f"من فضلك أرسل باقي {expected - received} مستند(ات).\n\n"
                f"✅ {received}/{expected} دستاویز موصول ہو گئی ہے۔\n"
                f"براہ کرم باقی {expected - received} دستاویز بھیج دیں۔"
            )
            _send_thread_reply(doc, msg)
        elif received == expected:
            _finalize_trip_and_kashf(contact, driver_name, trip)
        else:  # received > expected
            msg = (
                f"ℹ️ You sent {received} documents, but expected {expected}.\n"
                f"We will process the first {expected} documents.\n\n"
                f"ℹ️ أرسلت {received} مستندات بينما العدد المتوقع {expected}.\n"
                f"سيتم معالجة أول {expected} مستندات.\n\n"
                f"ℹ️ آپ نے {received} دستاویزات بھیجیں، جبکہ متوقع {expected} تھیں۔\n"
                f"پہلی {expected} دستاویزات پر عمل ہوگا۔"
            )
            _send_thread_reply(doc, msg)


# ---------------------------------------------------------------------------
# Driver & Trip helpers
# ---------------------------------------------------------------------------
def _digits_only(phone: str) -> str:
    """Keep only digits, used for tolerant matching."""
    return "".join(ch for ch in (phone or "") if ch.isdigit())

def _find_driver_by_phone(phone: str):
    """
    Resolve Staff from WhatsApp number using Staff.mobile_no ONLY.

    We do a relaxed LIKE search on the LAST digits of the number so it works for:
    - 923003764818
    - +923003764818
    - 0300-3764818
    - 03003764818
    """
    phone = normalize_phone(phone)
    if not phone:
        return None

    # keep only digits
    digits = "".join(ch for ch in phone if ch.isdigit())
    if not digits:
        return None

    # build candidates: full, last 10, last 9
    candidates = set()
    candidates.add(digits)
    if len(digits) >= 10:
        candidates.add(digits[-10:])
    if len(digits) >= 9:
        candidates.add(digits[-9:])

    # Try longest tails first
    for tail in sorted(candidates, key=len, reverse=True):
        rows = frappe.get_all(
            "Staff",
            filters={"mobile_no": ["like", f"%{tail}%"]},
            fields=["name", "mobile_no"],
            limit=1,
        )
        if rows:
            return rows[0]["name"]

    # nothing found
    return None


def _get_or_create_trip_for_contact(driver_name: str, contact):
    """
    If contact.current_trip is active (Scheduled/Departed) -> reuse.
    Otherwise create new Trip for this driver and link to contact.current_trip.
    """
    trip = None
    current_trip_name = getattr(contact, "current_trip", None)

    if current_trip_name and frappe.db.exists("Trip", current_trip_name):
        t = frappe.get_doc("Trip", current_trip_name)
        if t.trip_status in ("Scheduled", "Departed"):
            trip = t

    if not trip:
        trip = _create_new_trip_for_driver(driver_name)
        _update_contact_state(contact, current_trip=trip.name)

    return trip


def _create_new_trip_for_driver(driver_name: str):
    """Create a minimal Trip; route can later be improved with Staff.default_route, etc."""
    trip = frappe.new_doc("Trip")
    trip.driver = driver_name

    # Optional: Staff.default_route (Link Route)
    default_route = frappe.db.get_value("Staff", driver_name, "default_route")
    if not default_route:
        default_route = frappe.db.get_value("Route", {}, "name")

    if default_route:
        trip.trip_route = default_route

    trip.trip_status = "Scheduled"
    trip.insert(ignore_permissions=True)
    return trip


# ---------------------------------------------------------------------------
# OCR + OCR History
# ---------------------------------------------------------------------------

def _create_ocr_history_and_run_ocr(message_doc, trip, file_url: str) -> bool:
    """
    Create OCR History row and run OCR engine.

    Returns True if OCR produced usable parsed data
    (full_name + id_no + nationality).
    """
    # find File linked to this WhatsApp Message (webhook created it)
    file_doc = None
    files = frappe.get_all(
        "File",
        filters={
            "attached_to_doctype": "WhatsApp Message",
            "attached_to_name": message_doc.name,
        },
        fields=["name"],
        order_by="creation desc",
        limit=1,
    )
    if files:
        file_doc = files[0]["name"]

    # 1) Create OCR History shell
    history = frappe.get_doc(
        {
            "doctype": "OCR History",
            "source": "WABA Image"
            if message_doc.content_type == "image"
            else "WABA Document",
            "ocr_engine": "Hybrid",  # or set dynamically later
            "reference_doctype": "WhatsApp Message",
            "reference_name": message_doc.name,
            "trip": trip.name,
            "file": file_doc,
        }
    )
    history.insert(ignore_permissions=True)

    # 2) Call OCR manager
    try:
        from tms.utils.ocr_manager import analyze_id_document
    except ImportError:
        # no OCR handler yet
        return False

    try:
        result = analyze_id_document(file_url=file_url)
    except Exception:
        return False

    if not isinstance(result, dict):
        return False

    # expected keys: full_name, id_no, nationality, raw_text, fixed_text, confidence, json_data
    history.full_name = result.get("full_name") or ""
    history.id_no = result.get("id_no") or ""
    history.nationality = result.get("nationality") or ""
    history.raw_text = result.get("raw_text") or ""
    history.fixed_text = result.get("fixed_text") or ""
    history.confidence = result.get("confidence") or 0

    json_payload = result.get("json_data") or {}
    try:
        history.json_data = json.dumps(json_payload, ensure_ascii=False, indent=2)
    except Exception:
        history.json_data = json.dumps(
            {"_raw": str(json_payload)}, ensure_ascii=False
        )

    history.save(ignore_permissions=True)

    # Consider success only if basic fields exist
    if history.full_name and history.id_no and history.nationality:
        return True

    return False


# ---------------------------------------------------------------------------
# Finalize trip & send Kashf
# ---------------------------------------------------------------------------

def _finalize_trip_and_kashf(contact, driver_name: str, trip):
    """
    When expected_passengers == received_images (or more),
    fill Passengers from OCR History and send Trip PDF via WhatsApp.
    """
    expected = int(getattr(contact, "expected_passengers", 0) or 0)
    received = int(getattr(contact, "received_images", 0) or 0)

    if expected <= 0 or received <= 0:
        return

    # 1) Get OCR History rows for this Trip
    ocr_rows = frappe.get_all(
        "OCR History",
        filters={"trip": trip.name},
        fields=["name", "full_name", "id_no", "nationality"],
        order_by="creation asc",
    )

    # Only use up to expected rows
    ocr_rows = ocr_rows[:expected]

    # 2) (Optional) Clear existing passengers if you want fresh data each time:
    # trip.set("passengers", [])

    # 3) Fill Passengers table from OCR
    for row in ocr_rows:
        passenger = trip.append("passengers", {})
        passenger.passenger_name = row.get("full_name") or ""
        passenger.idpassport_no = row.get("id_no") or ""
        passenger.nationality = row.get("nationality") or ""

    trip.save(ignore_permissions=True)
    trip.add_comment(
        "Info", f"Passengers auto-filled from WhatsApp OCR at {now_datetime()}."
    )

    # 4) Send Kashf (Trip PDF) via existing function
    try:
        send_trip_pdf_via_whatsapp(trip.name)
    except Exception:
        frappe.log_error("Kashf send failed", f"Trip: {trip.name}")

    # 5) Inform driver in 3 languages (non-thread message is OK here)
    sender_no = contact.whatsapp_id
    msg = (
        "✅ All passenger documents received. Your Kashf for this trip has been prepared and sent.\n"
        "✅ تم استلام جميع مستندات الركاب. تم تجهيز كشف الرحلة وإرساله لك.\n"
        "✅ تمام، سب مسافروں کے دستاویزات موصول ہوگئے۔ آپ کا سفر کا کشف تیار ہو کر بھیج دیا گیا ہے۔"
    )
    _send_plain_message(sender_no, msg)

    # 6) Reset bot state for next trip
    _update_contact_state(
        contact,
        bot_state="DONE",
        expected_passengers=0,
        received_images=0,
        # keep current_trip so you can see last trip on contact
    )


# ---------------------------------------------------------------------------
# WhatsApp send helpers (local)
# ---------------------------------------------------------------------------

def _send_thread_reply(incoming_doc, message: str):
    """Create a reply message (is_reply=1, uses incoming.message_id)."""
    to = normalize_phone(
        getattr(incoming_doc, "from_", "") or getattr(incoming_doc, "from", "") or ""
    )
    if not to:
        return

    reply = frappe.get_doc(
        {
            "doctype": "WhatsApp Message",
            "type": "Outgoing",
            "to": to,
            "content_type": "text",
            "message": message,
            "message_type": "Manual",
            "is_reply": 1,
            "reply_to_message_id": incoming_doc.message_id,
        }
    )
    reply.insert(ignore_permissions=True)
    return reply.name


def _send_plain_message(to: str, message: str):
    """Non-thread text message (for final Kashf notification)."""
    to = normalize_phone(to)
    if not to:
        return

    msg = frappe.get_doc(
        {
            "doctype": "WhatsApp Message",
            "type": "Outgoing",
            "to": to,
            "content_type": "text",
            "message": message,
            "message_type": "Manual",
        }
    )
    msg.insert(ignore_permissions=True)
    return msg.name

# import json
# import frappe
# from frappe.utils import now_datetime

# from tms.utils.whatsapp_utils import (
#     normalize_phone,
#     get_or_create_contact,
#     send_trip_pdf_via_whatsapp,
# )


# # ---------------------------------------------------------------------------
# # Entry point: after_insert on WhatsApp Message
# # ---------------------------------------------------------------------------

# def handle_incoming_whatsapp(doc, event=None):
#     """Hook: called on after_insert of WhatsApp Message."""
#     # only care about Incoming
#     if doc.type != "Incoming":
#         return

#     content_type = (doc.content_type or "").lower()

#     # sender info
#     sender_no = normalize_phone(getattr(doc, "from_", "") or getattr(doc, "from", "") or "")
#     profile_name = (doc.profile_name or "").strip()

#     # ensure contact row exists
#     contact = get_or_create_contact(sender_no, profile_name)

#     if content_type == "text":
#         _handle_text_message(doc, contact)
#     elif content_type in ("image", "document"):
#         _handle_media_message(doc, contact)
#     else:
#         # ignore reactions, buttons, etc for now
#         return


# # ---------------------------------------------------------------------------
# # Contact helpers
# # ---------------------------------------------------------------------------

# def _update_contact_state(contact, **kwargs):
#     """Update WhatsApp Contact fields safely."""
#     if not contact:
#         return

#     dirty = False
#     for field, value in kwargs.items():
#         # Frappe will error if field doesn't exist – user must create fields in DocType
#         if hasattr(contact, field):
#             setattr(contact, field, value)
#             dirty = True

#     if dirty:
#         contact.save(ignore_permissions=True)


# # ---------------------------------------------------------------------------
# # Text handler (passenger count)
# # ---------------------------------------------------------------------------

# def _handle_text_message(doc, contact):
#     """Handle incoming text based on contact.bot_state."""
#     if not contact:
#         return

#     state = (getattr(contact, "bot_state", "") or "").upper()
#     text = (doc.message or "").strip()

#     # Only one state for now: expecting passenger count
#     if state == "ASKED_PASSENGERS":
#         num = _extract_int(text)
#         if not num or num <= 0:
#             msg = (
#                 "Please send only the number of passengers.\n"
#                 "من فضلك أرسل عدد الركاب كرقم فقط.\n"
#                 "براہ کرم صرف مسافروں کی تعداد نمبر میں بھیجیں۔"
#             )
#             _send_thread_reply(doc, msg)
#             return

#         # Set expected_passengers & move to COLLECTING_DOCS
#         received = int(getattr(contact, "received_images", 0) or 0)
#         _update_contact_state(
#             contact,
#             expected_passengers=num,
#             bot_state="COLLECTING_DOCS",
#         )

#         # If already received some docs, inform status
#         remaining = max(num - received, 0)

#         if received == 0:
#             msg = (
#                 f"✅ Got it. You said {num} passengers.\n"
#                 f"Please send {num} clear images or PDFs (Iqama / Passport / Visa / Nusuk), "
#                 f"one document per passenger.\n\n"
#                 f"✅ تم التأكيد. عدد الركاب {num}.\n"
#                 f"من فضلك أرسل {num} صورًا أو ملفات PDF واضحة (إقامة / جواز سفر / تأشيرة / نسك)، "
#                 f"لكل راكب مستند واحد.\n\n"
#                 f"✅ ٹھیک ہے، آپ نے {num} مسافروں کا بتایا ہے۔\n"
#                 f"براہ کرم {num} صاف تصویریں یا پی ڈی ایف بھیجیں (اقامہ / پاسپورٹ / ویزا / نسک)، "
#                 f"ہر مسافر کے لیے ایک دستاویز۔"
#             )
#         elif remaining > 0:
#             msg = (
#                 f"✅ I registered {num} passengers.\n"
#                 f"I already received {received} document(s). "
#                 f"Please send remaining {remaining} document(s).\n\n"
#                 f"✅ تم تسجيل {num} ركاب.\n"
#                 f"تم استلام {received} مستند(ات) حتى الآن. "
#                 f"من فضلك أرسل باقي {remaining} مستند(ات).\n\n"
#                 f"✅ {num} مسافروں کا اندراج ہوگیا ہے۔\n"
#                 f"اب تک {received} دستاویزات موصول ہو چکی ہیں۔ "
#                 f"براہ کرم باقی {remaining} دستاویز بھیجیں۔"
#             )
#         else:
#             # already have enough docs → finalize immediately
#             sender_no = contact.whatsapp_id
#             driver_name = _find_driver_by_phone(sender_no)
#             trip = _get_or_create_trip_for_contact(driver_name, contact)
#             _finalize_trip_and_kashf(contact, driver_name, trip)
#             # no extra message here; finalize function will send

#             return

#         _send_thread_reply(doc, msg)

#     # other states ignored for now
#     return


# def _extract_int(text: str) -> int | None:
#     """Extract first integer from text."""
#     digits = ""
#     for ch in text:
#         if ch.isdigit():
#             digits += ch
#         elif digits:
#             break
#     if not digits:
#         return None
#     try:
#         return int(digits)
#     except Exception:
#         return None


# # ---------------------------------------------------------------------------
# # Media handler (image / doc)
# # ---------------------------------------------------------------------------

# def _handle_media_message(doc, contact):
#     """Handle incoming image or PDF (WABA Document)."""
#     if not contact:
#         return

#     sender_no = normalize_phone(getattr(doc, "from_", "") or getattr(doc, "from", "") or "")
#     if not sender_no:
#         return

#     # 1) Resolve driver (Staff.mobile_no)
#     driver_name = _find_driver_by_phone(sender_no)
#     if not driver_name:
#         _send_thread_reply(
#             doc,
#             "⚠️ Your number is not registered as a driver in the system.\n"
#             "⚠️ رقمك غير مسجل كسائق في النظام.\n"
#             "⚠️ آپ کا نمبر سسٹم میں ڈرائیور کے طور پر رجسٹر نہیں ہے۔"
#         )
#         return

#     # 2) Get or create Trip bound to this contact
#     trip = _get_or_create_trip_for_contact(driver_name, contact)

#     # 3) Get file_url from WhatsApp Message.attach (created by webhook)
#     file_url = (doc.attach or "").strip()
#     if not file_url:
#         _send_thread_reply(
#             doc,
#             "🕐 I received your message, but no document/image was attached.\n"
#             "🕐 تم استلام رسالتك، لكن لا يوجد مستند أو صورة مرفقة.\n"
#             "🕐 میسج ملا لیکن کوئی تصویر یا دستاویز منسلک نہیں تھی۔"
#         )
#         return

#     # 4) Run OCR + create OCR History record
#     ocr_ok = _create_ocr_history_and_run_ocr(doc, trip, file_url)

#     if not ocr_ok:
#         # do NOT increment received_images, ask to resend this image
#         msg = (
#             "⚠️ This document image is not clear, please send a new clearer image.\n"
#             "⚠️ صورة هذا المستند غير واضحة، من فضلك أرسل صورة أوضح.\n"
#             "⚠️ اس دستاویز کی تصویر واضح نہیں ہے، براہ کرم نئی صاف تصویر بھیجیں۔"
#         )
#         _send_thread_reply(doc, msg)
#         return

#     # 5) Increment received_images
#     received = int(getattr(contact, "received_images", 0) or 0) + 1
#     expected = int(getattr(contact, "expected_passengers", 0) or 0)

#     # If we never asked passenger count yet, ask now (but keep received counter)
#     if expected <= 0 and (getattr(contact, "bot_state", "") or "").upper() not in ("ASKED_PASSENGERS", "COLLECTING_DOCS"):
#         _update_contact_state(contact, received_images=received, bot_state="ASKED_PASSENGERS")

#         msg = (
#             "🧾 I received your document.\n"
#             "How many passengers are going on this trip?\n\n"
#             "🧾 تم استلام مستندك.\n"
#             "كم عدد الركاب في هذه الرحلة؟\n\n"
#             "🧾 آپ کی دستاویز موصول ہوگئی ہے۔\n"
#             "اس سفر پر کتنے مسافر جائیں گے؟"
#         )
#         _send_thread_reply(doc, msg)
#         return

#     # If expected already known, update state and inform
#     _update_contact_state(contact, received_images=received, bot_state="COLLECTING_DOCS")

#     if expected > 0:
#         if received < expected:
#             msg = (
#                 f"✅ Document {received}/{expected} received.\n"
#                 f"Please send the remaining {expected - received} document(s).\n\n"
#                 f"✅ تم استلام المستند رقم {received} من {expected}.\n"
#                 f"من فضلك أرسل باقي {expected - received} مستند(ات).\n\n"
#                 f"✅ {received}/{expected} دستاویز موصول ہو گئی ہے۔\n"
#                 f"براہ کرم باقی {expected - received} دستاویز بھیج دیں۔"
#             )
#             _send_thread_reply(doc, msg)
#         elif received == expected:
#             _finalize_trip_and_kashf(contact, driver_name, trip)
#         else:  # received > expected
#             msg = (
#                 f"ℹ️ You sent {received} documents, but expected {expected}.\n"
#                 f"We will process the first {expected} documents.\n\n"
#                 f"ℹ️ أرسلت {received} مستندات بينما العدد المتوقع {expected}.\n"
#                 f"سيتم معالجة أول {expected} مستندات.\n\n"
#                 f"ℹ️ آپ نے {received} دستاویزات بھیجیں، جبکہ متوقع {expected} تھیں۔\n"
#                 f"پہلی {expected} دستاویزات پر عمل ہوگا۔"
#             )
#             _send_thread_reply(doc, msg)


# # ---------------------------------------------------------------------------
# # Driver & Trip helpers
# # ---------------------------------------------------------------------------

# def _find_driver_by_phone(phone: str):
#     """Resolve Staff from WhatsApp number."""
#     phone = normalize_phone(phone)
#     candidates = {phone}

#     if phone.startswith("+"):
#         candidates.add(phone[1:])
#     if phone.startswith("00"):
#         candidates.add(phone[2:])

#     # you can add more normalization if needed

#     return frappe.db.get_value(
#         "Staff",
#         {"mobile_no": ["in", list(candidates)]},
#         "name",
#     )


# def _get_or_create_trip_for_contact(driver_name: str, contact):
#     """
#     If contact.current_trip is active (Scheduled/Departed) -> reuse.
#     Otherwise create new Trip for this driver and link to contact.current_trip.
#     """
#     trip = None
#     current_trip_name = getattr(contact, "current_trip", None)

#     if current_trip_name and frappe.db.exists("Trip", current_trip_name):
#         t = frappe.get_doc("Trip", current_trip_name)
#         if t.trip_status in ("Scheduled", "Departed"):
#             trip = t

#     if not trip:
#         trip = _create_new_trip_for_driver(driver_name)
#         _update_contact_state(contact, current_trip=trip.name)

#     return trip


# def _create_new_trip_for_driver(driver_name: str):
#     """Create a minimal Trip; route can later be improved with Staff.default_route, etc."""
#     trip = frappe.new_doc("Trip")
#     trip.driver = driver_name

#     # Optional: Staff.default_route (Link Route)
#     default_route = frappe.db.get_value("Staff", driver_name, "default_route")
#     if not default_route:
#         default_route = frappe.db.get_value("Route", {}, "name")

#     if default_route:
#         trip.trip_route = default_route

#     trip.trip_status = "Scheduled"
#     trip.insert(ignore_permissions=True)
#     return trip


# # ---------------------------------------------------------------------------
# # OCR + OCR History
# # ---------------------------------------------------------------------------

# def _create_ocr_history_and_run_ocr(message_doc, trip, file_url: str) -> bool:
#     """
#     Create OCR History row and run OCR engine.

#     Returns True if OCR produced usable parsed data
#     (full_name + id_no + nationality).
#     """
#     # find File linked to this WhatsApp Message (webhook created it)
#     file_doc = None
#     files = frappe.get_all(
#         "File",
#         filters={
#             "attached_to_doctype": "WhatsApp Message",
#             "attached_to_name": message_doc.name,
#         },
#         fields=["name"],
#         order_by="creation desc",
#         limit=1,
#     )
#     if files:
#         file_doc = files[0]["name"]

#     # 1) Create OCR History shell
#     history = frappe.get_doc({
#         "doctype": "OCR History",
#         "source": "WABA Image" if message_doc.content_type == "image" else "WABA Document",
#         "ocr_engine": "Hybrid",  # or set dynamically later
#         "reference_doctype": "WhatsApp Message",
#         "reference_name": message_doc.name,
#         "trip": trip.name,
#         "file": file_doc,
#     })
#     history.insert(ignore_permissions=True)

#     # 2) Call OCR manager
#     try:
#         from tms.utils.ocr_manager import analyze_id_document
#     except ImportError:
#         # no OCR handler yet
#         return False

#     try:
#         result = analyze_id_document(file_url=file_url)
#     except Exception:
#         return False

#     if not isinstance(result, dict):
#         return False

#     # expected keys: full_name, id_no, nationality, raw_text, fixed_text, confidence, json_data
#     history.full_name = result.get("full_name") or ""
#     history.id_no = result.get("id_no") or ""
#     history.nationality = result.get("nationality") or ""
#     history.raw_text = result.get("raw_text") or ""
#     history.fixed_text = result.get("fixed_text") or ""
#     history.confidence = result.get("confidence") or 0

#     json_payload = result.get("json_data") or {}
#     try:
#         history.json_data = json.dumps(json_payload, ensure_ascii=False, indent=2)
#     except Exception:
#         history.json_data = json.dumps({"_raw": str(json_payload)}, ensure_ascii=False)

#     history.save(ignore_permissions=True)

#     # Consider success only if basic fields exist
#     if history.full_name and history.id_no and history.nationality:
#         return True

#     return False


# # ---------------------------------------------------------------------------
# # Finalize trip & send Kashf
# # ---------------------------------------------------------------------------

# def _finalize_trip_and_kashf(contact, driver_name: str, trip):
#     """
#     When expected_passengers == received_images (or more),
#     fill Passengers from OCR History and send Trip PDF via WhatsApp.
#     """
#     expected = int(getattr(contact, "expected_passengers", 0) or 0)
#     received = int(getattr(contact, "received_images", 0) or 0)

#     if expected <= 0 or received <= 0:
#         return

#     # 1) Get OCR History rows for this Trip
#     ocr_rows = frappe.get_all(
#         "OCR History",
#         filters={"trip": trip.name},
#         fields=["name", "full_name", "id_no", "nationality"],
#         order_by="creation asc",
#     )

#     # Only use up to expected rows
#     ocr_rows = ocr_rows[:expected]

#     # 2) Clear existing passengers? (optional)
#     # If you want to always rebuild:
#     # trip.set("passengers", [])

#     # 3) Fill Passengers table from OCR
#     for row in ocr_rows:
#         passenger = trip.append("passengers", {})
#         passenger.passenger_name = row.get("full_name") or ""
#         passenger.idpassport_no = row.get("id_no") or ""
#         passenger.nationality = row.get("nationality") or ""

#     trip.save(ignore_permissions=True)
#     trip.add_comment(
#         "Info",
#         f"Passengers auto-filled from WhatsApp OCR at {now_datetime()}."
#     )

#     # 4) Send Kashf (Trip PDF) via existing function
#     try:
#         send_trip_pdf_via_whatsapp(trip.name)
#     except Exception:
#         frappe.log_error("Kashf send failed", f"Trip: {trip.name}")

#     # 5) Inform driver in 3 languages (non-thread message is OK here)
#     sender_no = contact.whatsapp_id
#     msg = (
#         "✅ All passenger documents received. Your Kashf for this trip has been prepared and sent.\n"
#         "✅ تم استلام جميع مستندات الركاب. تم تجهيز كشف الرحلة وإرساله لك.\n"
#         "✅ تمام، سب مسافروں کے دستاویزات موصول ہوگئے۔ آپ کا سفر کا کشف تیار ہو کر بھیج دیا گیا ہے۔"
#     )
#     _send_plain_message(sender_no, msg)

#     # 6) Reset bot state for next trip
#     _update_contact_state(
#         contact,
#         bot_state="DONE",
#         expected_passengers=0,
#         received_images=0,
#         # keep current_trip so you can see last trip on contact
#     )


# # ---------------------------------------------------------------------------
# # WhatsApp send helpers (local)
# # ---------------------------------------------------------------------------

# def _send_thread_reply(incoming_doc, message: str):
#     """Create a reply message (is_reply=1, uses incoming.message_id)."""
#     to = normalize_phone(getattr(incoming_doc, "from_", "") or getattr(incoming_doc, "from", "") or "")
#     if not to:
#         return

#     reply = frappe.get_doc({
#         "doctype": "WhatsApp Message",
#         "type": "Outgoing",
#         "to": to,
#         "content_type": "text",
#         "message": message,
#         "message_type": "Manual",
#         "is_reply": 1,
#         "reply_to_message_id": incoming_doc.message_id,
#     })
#     reply.insert(ignore_permissions=True)
#     return reply.name


# def _send_plain_message(to: str, message: str):
#     """Non-thread text message (for final Kashf notification)."""
#     to = normalize_phone(to)
#     if not to:
#         return

#     msg = frappe.get_doc({
#         "doctype": "WhatsApp Message",
#         "type": "Outgoing",
#         "to": to,
#         "content_type": "text",
#         "message": message,
#         "message_type": "Manual",
#     })
#     msg.insert(ignore_permissions=True)
#     return msg.name

# import json
# import frappe
# from frappe.utils import now_datetime

# from tms.utils.whatsapp_utils import (
#     normalize_phone,
#     get_or_create_contact,
#     send_trip_pdf_via_whatsapp,
# )


# # ---------------------------------------------------------------------------
# # Entry point: after_insert on WhatsApp Message
# # ---------------------------------------------------------------------------

# def handle_incoming_whatsapp(doc, event=None):
#     """Hook: called on after_insert of WhatsApp Message."""
#     # only care about Incoming
#     if doc.type != "Incoming":
#         return

#     content_type = (doc.content_type or "").lower()

#     # sender info
#     sender_no = normalize_phone(getattr(doc, "from_", "") or getattr(doc, "from", "") or "")
#     profile_name = (doc.profile_name or "").strip()

#     # ensure contact row exists
#     contact = get_or_create_contact(sender_no, profile_name)

#     if content_type == "text":
#         _handle_text_message(doc, contact)
#     elif content_type in ("image", "document"):
#         _handle_media_message(doc, contact)
#     else:
#         # ignore reactions, buttons, etc for now
#         return


# # ---------------------------------------------------------------------------
# # Contact helpers
# # ---------------------------------------------------------------------------

# def _update_contact_state(contact, **kwargs):
#     """Update WhatsApp Contact fields safely."""
#     if not contact:
#         return

#     dirty = False
#     for field, value in kwargs.items():
#         # Frappe will error if field doesn't exist – user must create fields in DocType
#         if hasattr(contact, field):
#             setattr(contact, field, value)
#             dirty = True

#     if dirty:
#         contact.save(ignore_permissions=True)


# # ---------------------------------------------------------------------------
# # Text handler (passenger count)
# # ---------------------------------------------------------------------------

# def _handle_text_message(doc, contact):
#     """Handle incoming text based on contact.bot_state."""
#     if not contact:
#         return

#     state = (getattr(contact, "bot_state", "") or "").upper()
#     text = (doc.message or "").strip()

#     # Only one state for now: expecting passenger count
#     if state == "ASKED_PASSENGERS":
#         num = _extract_int(text)
#         if not num or num <= 0:
#             msg = (
#                 "Please send only the number of passengers.\n"
#                 "من فضلك أرسل عدد الركاب كرقم فقط.\n"
#                 "براہ کرم صرف مسافروں کی تعداد نمبر میں بھیجیں۔"
#             )
#             _send_thread_reply(doc, msg)
#             return

#         # Set expected_passengers & move to COLLECTING_DOCS
#         received = int(getattr(contact, "received_images", 0) or 0)
#         _update_contact_state(
#             contact,
#             expected_passengers=num,
#             bot_state="COLLECTING_DOCS",
#         )

#         # If already received some docs, inform status
#         remaining = max(num - received, 0)

#         if received == 0:
#             msg = (
#                 f"✅ Got it. You said {num} passengers.\n"
#                 f"Please send {num} clear images or PDFs (Iqama / Passport / Visa / Nusuk), "
#                 f"one document per passenger.\n\n"
#                 f"✅ تم التأكيد. عدد الركاب {num}.\n"
#                 f"من فضلك أرسل {num} صورًا أو ملفات PDF واضحة (إقامة / جواز سفر / تأشيرة / نسك)، "
#                 f"لكل راكب مستند واحد.\n\n"
#                 f"✅ ٹھیک ہے، آپ نے {num} مسافروں کا بتایا ہے۔\n"
#                 f"براہ کرم {num} صاف تصویریں یا پی ڈی ایف بھیجیں (اقامہ / پاسپورٹ / ویزا / نسک)، "
#                 f"ہر مسافر کے لیے ایک دستاویز۔"
#             )
#         elif remaining > 0:
#             msg = (
#                 f"✅ I registered {num} passengers.\n"
#                 f"I already received {received} document(s). "
#                 f"Please send remaining {remaining} document(s).\n\n"
#                 f"✅ تم تسجيل {num} ركاب.\n"
#                 f"تم استلام {received} مستند(ات) حتى الآن. "
#                 f"من فضلك أرسل باقي {remaining} مستند(ات).\n\n"
#                 f"✅ {num} مسافروں کا اندراج ہوگیا ہے۔\n"
#                 f"اب تک {received} دستاویزات موصول ہو چکی ہیں۔ "
#                 f"براہ کرم باقی {remaining} دستاویز بھیجیں۔"
#             )
#         else:
#             # already have enough docs → finalize immediately
#             sender_no = contact.whatsapp_id
#             driver_name = _find_driver_by_phone(sender_no)
#             trip = _get_or_create_trip_for_contact(driver_name, contact)
#             _finalize_trip_and_kashf(contact, driver_name, trip)
#             # no extra message here; finalize function will send

#             return

#         _send_thread_reply(doc, msg)

#     # other states ignored for now
#     return


# def _extract_int(text: str) -> int | None:
#     """Extract first integer from text."""
#     digits = ""
#     for ch in text:
#         if ch.isdigit():
#             digits += ch
#         elif digits:
#             break
#     if not digits:
#         return None
#     try:
#         return int(digits)
#     except Exception:
#         return None


# # ---------------------------------------------------------------------------
# # Media handler (image / doc)
# # ---------------------------------------------------------------------------

# def _handle_media_message(doc, contact):
#     """Handle incoming image or PDF (WABA Document)."""
#     if not contact:
#         return

#     sender_no = normalize_phone(getattr(doc, "from_", "") or getattr(doc, "from", "") or "")
#     if not sender_no:
#         return

#     # 1) Resolve driver (Staff.mobile_no)
#     driver_name = _find_driver_by_phone(sender_no)
#     if not driver_name:
#         _send_thread_reply(
#             doc,
#             "⚠️ Your number is not registered as a driver in the system.\n"
#             "⚠️ رقمك غير مسجل كسائق في النظام.\n"
#             "⚠️ آپ کا نمبر سسٹم میں ڈرائیور کے طور پر رجسٹر نہیں ہے۔"
#         )
#         return

#     # 2) Get or create Trip bound to this contact
#     trip = _get_or_create_trip_for_contact(driver_name, contact)

#     # 3) Get file_url from WhatsApp Message.attach (created by webhook)
#     file_url = (doc.attach or "").strip()
#     if not file_url:
#         _send_thread_reply(
#             doc,
#             "🕐 I received your message, but no document/image was attached.\n"
#             "🕐 تم استلام رسالتك، لكن لا يوجد مستند أو صورة مرفقة.\n"
#             "🕐 میسج ملا لیکن کوئی تصویر یا دستاویز منسلک نہیں تھی۔"
#         )
#         return

#     # 4) Run OCR + create OCR History record
#     ocr_ok = _create_ocr_history_and_run_ocr(doc, trip, file_url)

#     if not ocr_ok:
#         # do NOT increment received_images, ask to resend this image
#         msg = (
#             "⚠️ This document image is not clear, please send a new clearer image.\n"
#             "⚠️ صورة هذا المستند غير واضحة، من فضلك أرسل صورة أوضح.\n"
#             "⚠️ اس دستاویز کی تصویر واضح نہیں ہے، براہ کرم نئی صاف تصویر بھیجیں۔"
#         )
#         _send_thread_reply(doc, msg)
#         return

#     # 5) Increment received_images
#     received = int(getattr(contact, "received_images", 0) or 0) + 1
#     expected = int(getattr(contact, "expected_passengers", 0) or 0)

#     # If we never asked passenger count yet, ask now (but keep received counter)
#     if expected <= 0 and (getattr(contact, "bot_state", "") or "").upper() not in ("ASKED_PASSENGERS", "COLLECTING_DOCS"):
#         _update_contact_state(contact, received_images=received, bot_state="ASKED_PASSENGERS")

#         msg = (
#             "🧾 I received your document.\n"
#             "How many passengers are going on this trip?\n\n"
#             "🧾 تم استلام مستندك.\n"
#             "كم عدد الركاب في هذه الرحلة؟\n\n"
#             "🧾 آپ کی دستاویز موصول ہوگئی ہے۔\n"
#             "اس سفر پر کتنے مسافر جائیں گے؟"
#         )
#         _send_thread_reply(doc, msg)
#         return

#     # If expected already known, update state and inform
#     _update_contact_state(contact, received_images=received, bot_state="COLLECTING_DOCS")

#     if expected > 0:
#         if received < expected:
#             msg = (
#                 f"✅ Document {received}/{expected} received.\n"
#                 f"Please send the remaining {expected - received} document(s).\n\n"
#                 f"✅ تم استلام المستند رقم {received} من {expected}.\n"
#                 f"من فضلك أرسل باقي {expected - received} مستند(ات).\n\n"
#                 f"✅ {received}/{expected} دستاویز موصول ہو گئی ہے۔\n"
#                 f"براہ کرم باقی {expected - received} دستاویز بھیج دیں۔"
#             )
#             _send_thread_reply(doc, msg)
#         elif received == expected:
#             _finalize_trip_and_kashf(contact, driver_name, trip)
#         else:  # received > expected
#             msg = (
#                 f"ℹ️ You sent {received} documents, but expected {expected}.\n"
#                 f"We will process the first {expected} documents.\n\n"
#                 f"ℹ️ أرسلت {received} مستندات بينما العدد المتوقع {expected}.\n"
#                 f"سيتم معالجة أول {expected} مستندات.\n\n"
#                 f"ℹ️ آپ نے {received} دستاویزات بھیجیں، جبکہ متوقع {expected} تھیں۔\n"
#                 f"پہلی {expected} دستاویزات پر عمل ہوگا۔"
#             )
#             _send_thread_reply(doc, msg)


# # ---------------------------------------------------------------------------
# # Driver & Trip helpers
# # ---------------------------------------------------------------------------

# def _digits_only(phone: str) -> str:
#     """Keep only digits, used for loose 'endswith' matching."""
#     return "".join(ch for ch in (phone or "") if ch.isdigit())


# def _find_driver_by_phone(phone: str):
#     """
#     Resolve *Staff* record for a real driver from WhatsApp number.

#     Rule:
#       - Find Staff by phone (mobile_no OR cell_number)
#       - Then check if this Staff is linked to a Driver
#         (Driver.staff or Driver.employee)
#       - Only then treat as valid driver.
#     """
#     if not phone:
#         return None

#     raw = normalize_phone(phone)
#     digits = _digits_only(raw)
#     if not digits:
#         return None

#     # We match last 9–12 digits to be tolerant (+966 / 00966 etc.)
#     candidates = set()
#     for n in range(9, 13):
#         if len(digits) >= n:
#             candidates.add(digits[-n:])

#     def _like_any(doctype: str, fieldname: str):
#         """Return first row where field LIKE %tail for any candidate."""
#         for tail in sorted(candidates, key=len, reverse=True):
#             rows = frappe.get_all(
#                 doctype,
#                 filters={fieldname: ["like", f"%{tail}"]},
#                 fields=["name", fieldname],
#                 limit=1,
#             )
#             if rows:
#                 return rows[0]
#         return None

#     # --- 1) Find Staff by mobile_no OR cell_number ---
#     staff_row = _like_any("Staff", "mobile_no")
#     if not staff_row:
#         staff_row = _like_any("Staff", "cell_number")

#     if not staff_row:
#         # no staff with this phone at all
#         return None

#     staff_name = staff_row["name"]

#     # --- 2) Check if this Staff is linked to a Driver record ---
#     if not frappe.db.exists("DocType", "Driver"):
#         # if you *require* core Driver as well, then treat as NOT driver
#         return None

#     # Try Driver.staff link
#     driver_name = frappe.db.get_value(
#         "Driver",
#         {"staff": staff_name},
#         "name",
#     )

#     # or Driver.employee link (depending on your customization)
#     if not driver_name:
#         driver_name = frappe.db.get_value(
#             "Driver",
#             {"employee": staff_name},
#             "name",
#         )

#     if not driver_name:
#         # Staff exists, but no linked Driver record → not a driver yet
#         return None

#     # ✅ OK: this WhatsApp number belongs to Staff that has a Driver record
#     return staff_name

# def _get_or_create_trip_for_contact(driver_name: str, contact):
#     """
#     If contact.current_trip is active (Scheduled/Departed) -> reuse.
#     Otherwise create new Trip for this driver and link to contact.current_trip.
#     """
#     trip = None
#     current_trip_name = getattr(contact, "current_trip", None)

#     if current_trip_name and frappe.db.exists("Trip", current_trip_name):
#         t = frappe.get_doc("Trip", current_trip_name)
#         if t.trip_status in ("Scheduled", "Departed"):
#             trip = t

#     if not trip:
#         trip = _create_new_trip_for_driver(driver_name)
#         _update_contact_state(contact, current_trip=trip.name)

#     return trip


# def _create_new_trip_for_driver(driver_name: str):
#     """Create a minimal Trip; route can later be improved with Staff.default_route, etc."""
#     trip = frappe.new_doc("Trip")
#     trip.driver = driver_name

#     # Optional: Staff.default_route (Link Route)
#     default_route = frappe.db.get_value("Staff", driver_name, "default_route")
#     if not default_route:
#         default_route = frappe.db.get_value("Route", {}, "name")

#     if default_route:
#         trip.trip_route = default_route

#     trip.trip_status = "Scheduled"
#     trip.insert(ignore_permissions=True)
#     return trip


# # ---------------------------------------------------------------------------
# # OCR + OCR History
# # ---------------------------------------------------------------------------

# def _create_ocr_history_and_run_ocr(message_doc, trip, file_url: str) -> bool:
#     """
#     Create OCR History row and run OCR engine.

#     Returns True if OCR produced usable parsed data
#     (full_name + id_no + nationality).
#     """
#     # find File linked to this WhatsApp Message (webhook created it)
#     file_doc = None
#     files = frappe.get_all(
#         "File",
#         filters={
#             "attached_to_doctype": "WhatsApp Message",
#             "attached_to_name": message_doc.name,
#         },
#         fields=["name"],
#         order_by="creation desc",
#         limit=1,
#     )
#     if files:
#         file_doc = files[0]["name"]

#     # 1) Create OCR History shell
#     history = frappe.get_doc({
#         "doctype": "OCR History",
#         "source": "WABA Image" if message_doc.content_type == "image" else "WABA Document",
#         "ocr_engine": "Hybrid",  # or set dynamically later
#         "reference_doctype": "WhatsApp Message",
#         "reference_name": message_doc.name,
#         "trip": trip.name,
#         "file": file_doc,
#     })
#     history.insert(ignore_permissions=True)

#     # 2) Call OCR manager
#     try:
#         from tms.utils.ocr_manager import analyze_id_document
#     except ImportError:
#         # no OCR handler yet
#         return False

#     try:
#         result = analyze_id_document(file_url=file_url)
#     except Exception:
#         return False

#     if not isinstance(result, dict):
#         return False

#     # expected keys: full_name, id_no, nationality, raw_text, fixed_text, confidence, json_data
#     history.full_name = result.get("full_name") or ""
#     history.id_no = result.get("id_no") or ""
#     history.nationality = result.get("nationality") or ""
#     history.raw_text = result.get("raw_text") or ""
#     history.fixed_text = result.get("fixed_text") or ""
#     history.confidence = result.get("confidence") or 0

#     json_payload = result.get("json_data") or {}
#     try:
#         history.json_data = json.dumps(json_payload, ensure_ascii=False, indent=2)
#     except Exception:
#         history.json_data = json.dumps({"_raw": str(json_payload)}, ensure_ascii=False)

#     history.save(ignore_permissions=True)

#     # Consider success only if basic fields exist
#     if history.full_name and history.id_no and history.nationality:
#         return True

#     return False


# # ---------------------------------------------------------------------------
# # Finalize trip & send Kashf
# # ---------------------------------------------------------------------------

# def _finalize_trip_and_kashf(contact, driver_name: str, trip):
#     """
#     When expected_passengers == received_images (or more),
#     fill Passengers from OCR History and send Trip PDF via WhatsApp.
#     """
#     expected = int(getattr(contact, "expected_passengers", 0) or 0)
#     received = int(getattr(contact, "received_images", 0) or 0)

#     if expected <= 0 or received <= 0:
#         return

#     # 1) Get OCR History rows for this Trip
#     ocr_rows = frappe.get_all(
#         "OCR History",
#         filters={"trip": trip.name},
#         fields=["name", "full_name", "id_no", "nationality"],
#         order_by="creation asc",
#     )

#     # Only use up to expected rows
#     ocr_rows = ocr_rows[:expected]

#     # 2) Clear existing passengers? (optional)
#     # If you want to always rebuild:
#     # trip.set("passengers", [])

#     # 3) Fill Passengers table from OCR
#     for row in ocr_rows:
#         passenger = trip.append("passengers", {})
#         passenger.passenger_name = row.get("full_name") or ""
#         passenger.idpassport_no = row.get("id_no") or ""
#         passenger.nationality = row.get("nationality") or ""

#     trip.save(ignore_permissions=True)
#     trip.add_comment(
#         "Info",
#         f"Passengers auto-filled from WhatsApp OCR at {now_datetime()}."
#     )

#     # 4) Send Kashf (Trip PDF) via existing function
#     try:
#         send_trip_pdf_via_whatsapp(trip.name)
#     except Exception:
#         frappe.log_error("Kashf send failed", f"Trip: {trip.name}")

#     # 5) Inform driver in 3 languages (non-thread message is OK here)
#     sender_no = contact.whatsapp_id
#     msg = (
#         "✅ All passenger documents received. Your Kashf for this trip has been prepared and sent.\n"
#         "✅ تم استلام جميع مستندات الركاب. تم تجهيز كشف الرحلة وإرساله لك.\n"
#         "✅ تمام، سب مسافروں کے دستاویزات موصول ہوگئے۔ آپ کا سفر کا کشف تیار ہو کر بھیج دیا گیا ہے۔"
#     )
#     _send_plain_message(sender_no, msg)

#     # 6) Reset bot state for next trip
#     _update_contact_state(
#         contact,
#         bot_state="DONE",
#         expected_passengers=0,
#         received_images=0,
#         # keep current_trip so you can see last trip on contact
#     )


# # ---------------------------------------------------------------------------
# # WhatsApp send helpers (local)
# # ---------------------------------------------------------------------------

# def _send_thread_reply(incoming_doc, message: str):
#     """Create a reply message (is_reply=1, uses incoming.message_id)."""
#     to = normalize_phone(getattr(incoming_doc, "from_", "") or getattr(incoming_doc, "from", "") or "")
#     if not to:
#         return

#     reply = frappe.get_doc({
#         "doctype": "WhatsApp Message",
#         "type": "Outgoing",
#         "to": to,
#         "content_type": "text",
#         "message": message,
#         "message_type": "Manual",
#         "is_reply": 1,
#         "reply_to_message_id": incoming_doc.message_id,
#     })
#     reply.insert(ignore_permissions=True)
#     return reply.name


# def _send_plain_message(to: str, message: str):
#     """Non-thread text message (for final Kashf notification)."""
#     to = normalize_phone(to)
#     if not to:
#         return

#     msg = frappe.get_doc({
#         "doctype": "WhatsApp Message",
#         "type": "Outgoing",
#         "to": to,
#         "content_type": "text",
#         "message": message,
#         "message_type": "Manual",
#     })
#     msg.insert(ignore_permissions=True)
#     return msg.name
