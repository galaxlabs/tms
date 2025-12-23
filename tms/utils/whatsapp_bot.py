# Last one
import re
import json
import frappe
from frappe.utils import nowdate, now_datetime, add_to_date
from tms.utils.whatsapp_utils import (
    normalize_phone,
    get_or_create_contact,
    send_trip_pdf_via_whatsapp,
)

def _ask_route_choice(doc, contact):
    """Ask driver to choose a Route from a numbered list and store options on contact."""
    routes = frappe.get_all(
        "Route",
        fields=["name"],
        order_by="name asc",
    )

    if not routes:
        _send_thread_reply(
            doc,
            "⚠ No routes are defined in the system. Please contact the office.\n"
            "⚠ لا توجد خطوط سير معرّفة في النظام. يرجى التواصل مع المكتب.\n"
            "⚠ سسٹم میں کوئی روٹ سیٹ نہیں کیا گیا۔ براہ کرم دفتر سے رابطہ کریں۔"
        )
        return

    options = [r["name"] for r in routes]

    # store list on contact so we can map 1..N back to Route name
    if hasattr(contact, "route_options_json"):
        contact.route_options_json = json.dumps(options, ensure_ascii=False)
    if hasattr(contact, "bot_state"):
        contact.bot_state = "ASKING_ROUTE"

    contact.save(ignore_permissions=True)

    # Build message with numbered list
    lines = [
        "🛣 Please choose your route by replying with the *number*:\n"
        "من فضلك اختر خط السير بإرسال *رقم الخيار*:\n"
        "براہ کرم نیچے دی گئی فہرست میں سے *نمبر* بھیج کر روٹ منتخب کریں:",
        "",
    ]
    for idx, name in enumerate(options, start=1):
        lines.append(f"{idx}. {name}")

    msg = "\n".join(lines)
    _send_thread_reply(doc, msg)

def handle_incoming_whatsapp(doc, event=None):
    """Hook: called on after_insert of WhatsApp Message."""
    frappe.set_user("whatsapp.bot@example.com")

    if doc.type != "Incoming":
        return

    frappe.set_user("whatsapp.bot@example.com")
    content_type = (doc.content_type or "").lower()

    sender_no_raw = (doc.get("from") or doc.get("from_") or "").strip()
    sender_no = normalize_phone(sender_no_raw)
    profile_name = (doc.profile_name or "").strip()

    frappe.log_error(
        f"RAW FROM: {sender_no_raw}\nNORMALIZED: {sender_no}",
        "TripBot Incoming FROM Debug",
    )

    contact = get_or_create_contact(sender_no, profile_name)

    # ✅ Update 24-hour window for ANY inbound message type (text/media/buttons/etc.)
    now = now_datetime()
    _update_contact_state(
        contact,
        last_inbound_at=now,
        conversation_expires_at=add_to_date(now, hours=24),
    )

    # Then handle supported types
    if content_type == "text":
        _handle_text_message(doc, contact)
    elif content_type in ("image", "document"):
        _handle_media_message(doc, contact)
    else:
        # Keep window updated even if you don't process this type
        return

# ---------------------------------------------------------------------------
# Contact helpers
# ---------------------------------------------------------------------------

def _update_contact_state(contact, **kwargs):
    """Update WhatsApp Contact fields safely."""
    if not contact:
        return

    dirty = False
    for field, value in kwargs.items():
        # Frappe will error if field doesn't exist – user must create fields in DocType
        if hasattr(contact, field):
            setattr(contact, field, value)
            dirty = True

    if dirty:
        contact.save(ignore_permissions=True)

def _handle_text_message(doc, contact):
    """Handle incoming text based on contact.bot_state."""
    if not contact:
        return

    state = (getattr(contact, "bot_state", "") or "").upper()
    text = (doc.message or "").strip()
    sender_no = contact.whatsapp_id
    driver_name = _find_driver_by_phone(sender_no)

    # SAFEGUARD: if we still don't know driver, just ignore advanced logic
    if not driver_name:
        return

    # -------------------------------------------------------
    # 1) State: ASKING_ROUTE  (driver chooses from Route list)
    # -------------------------------------------------------
    if state == "ASKING_ROUTE":
        num = _extract_int(text)

        if not num or num <= 0:
            _send_thread_reply(
                doc,
                "❗ Please reply with the *number* of the route from the list.\n"
                "❗ من فضلك أرسل *رقم* خط السير من القائمة.\n"
                "❗ براہ کرم لسٹ میں سے روٹ کا *نمبر* بھیجیں۔"
            )
            return

        options_raw = getattr(contact, "route_options_json", "") or ""
        try:
            options = json.loads(options_raw) if options_raw else []
        except Exception:
            options = []

        if not options or num > len(options):
            _send_thread_reply(
                doc,
                "❗ Invalid option. Please reply with a valid route number from the list.\n"
                "❗ خيار غير صالح. من فضلك أرسل رقم صحيح من القائمة.\n"
                "❗ غلط آپشن۔ براہ کرم لسٹ میں سے درست نمبر بھیجیں۔"
            )
            return

        chosen_route = options[num - 1]

        # Save chosen route on contact
        if hasattr(contact, "preferred_route"):
            contact.preferred_route = chosen_route
        contact.bot_state = "ROUTE_SET"
        contact.route_options_json = ""
        contact.save(ignore_permissions=True)

        # Update the current Trip with this route
        trip = _get_or_create_trip_for_contact(driver_name, contact)
        if trip.trip_route != chosen_route:
            trip.trip_route = chosen_route
            trip.save(ignore_permissions=True)

        # Maybe now we can finalize (if we already have all docs & passenger count)
        if _maybe_finalize_trip(contact, driver_name, trip):
            return

        msg = (
            f"✅ Route selected: {chosen_route}.\n"
            "If any passenger documents are still pending, please send them now.\n\n"
            "✅ تم اختيار خط السير: {route}.\n"
            "إذا كانت هناك مستندات ركاب متبقية، من فضلك أرسلها الآن.\n\n"
            "✅ روٹ منتخب ہو گیا: {route}.\n"
            "اگر کوئی مسافر کی دستاویزات باقی ہوں تو براہ کرم اب بھیج دیں۔"
        ).replace("{route}", chosen_route)
        _send_thread_reply(doc, msg)
        return

    # -------------------------------------------------------
    # 2) Default / WAITING_PASSENGER_COUNT / COLLECTING_DOCS:
    #    treat numeric text as passenger count
    # -------------------------------------------------------
    num = _extract_int(text)
    if not num or num <= 0:
        # don't spam; just soft guidance
        msg = (
            "ℹ️ If you are confirming passengers, please send the *number of passengers* only.\n"
            "ℹ️ إذا كنت تؤكد عدد الركاب، من فضلك أرسل *عدد الركاب* فقط.\n"
            "ℹ️ اگر آپ مسافروں کی تعداد بتانا چاہتے ہیں، تو براہ کرم صرف *مسافروں کی تعداد* نمبر میں بھیجیں۔"
        )
        _send_thread_reply(doc, msg)
        return

    expected = num
    received = int(getattr(contact, "received_images", 0) or 0)

    # Save expected passengers and set state
    _update_contact_state(
        contact,
        expected_passengers=expected,
        bot_state="COLLECTING_DOCS",
    )

    trip = _get_or_create_trip_for_contact(driver_name, contact)

    # CASE A: no documents yet → ask to send docs
    if received == 0:
        msg = (
            f"✅ Got it. You said {expected} passengers.\n"
            f"Please send {expected} clear images or PDFs (Iqama / Passport / Visa / Nusuk), "
            f"one document per passenger.\n\n"
            f"✅ تم التأكيد. عدد الركاب {expected}.\n"
            f"من فضلك أرسل {expected} صورًا أو ملفات PDF واضحة (إقامة / جواز سفر / تأشيرة / نسك)، "
            f"لكل راكب مستند واحد.\n\n"
            f"✅ ٹھیک ہے، آپ نے {expected} مسافروں کا بتایا ہے۔\n"
            f"براہ کرم {expected} صاف تصویریں یا پی ڈی ایف بھیجیں (اقامہ / پاسپورٹ / ویزا / نسک)، "
            f"ہر مسافر کے لیے ایک دستاویز۔"
        )
        _send_thread_reply(doc, msg)
        return

    # CASE B: some docs already received
    if received < expected:
        remaining = expected - received
        msg = (
            f"✅ I registered {expected} passengers.\n"
            f"I already received {received} document(s). "
            f"Please send remaining {remaining} document(s).\n\n"
            f"✅ تم تسجيل {expected} ركاب.\n"
            f"تم استلام {received} مستند(ات) حتى الآن. "
            f"من فضلك أرسل باقي {remaining} مستند(ات).\n\n"
            f"✅ {expected} مسافروں کا اندراج ہو گیا ہے۔\n"
            f"اب تک {received} دستاویزات موصول ہو چکی ہیں۔ "
            f"براہ کرم باقی {remaining} دستاویز بھیجیں۔"
        )
        _send_thread_reply(doc, msg)
        return

    # CASE C: received >= expected → now ask for route if not set
    if not getattr(contact, "preferred_route", None):
        _ask_route_choice(doc, contact)
        return

    # CASE D: everything is ready (route already chosen) → finalize
    if _maybe_finalize_trip(contact, driver_name, trip):
        return



def _extract_int(text: str) -> int | None:
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

def _handle_media_message(doc, contact):
    """Handle incoming image or PDF (WhatsApp Message)."""
    if not contact:
        return

    sender_no = normalize_phone(
        getattr(doc, "from_", "") or getattr(doc, "from", "") or ""
    )
    if not sender_no:
        return

    # 1) Resolve driver (Staff.mobile_no)
    driver_name = _find_driver_by_phone(sender_no)
    if not driver_name:
        _send_thread_reply(
            doc,
            "⚠️ Your number is not registered as a driver in the system.\n"
            "⚠️ رقمك غير مسجل كسائق في النظام.\n"
            "⚠️ آپ کا نمبر سسٹم میں ڈرائیور کے طور پر رجسٹر نہیں ہے۔"
        )
        return

    # 2) Ensure we have a Trip bound to this driver/contact
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
    state = (getattr(contact, "bot_state", "") or "").upper()

    # Update counters/state
    new_state = state
    if expected <= 0:
        # We still don't know passenger count yet
        new_state = "WAITING_PASSENGER_COUNT"
    else:
        new_state = "COLLECTING_DOCS"

    _update_contact_state(
        contact,
        received_images=received,
        bot_state=new_state,
    )

    # 6) If we already know expected passengers & route, maybe finalize now
    if _maybe_finalize_trip(contact, driver_name, trip):
        return

    # 7) Reply to driver based on whether we know passenger count
    if expected <= 0:
        # We don't know yet how many passengers → ask for count
        msg = (
            f"🧾 Document {received} received.\n"
            "When you finish sending all passenger documents, "
            "please reply with the *number of passengers*.\n\n"
            "🧾 تم استلام المستند رقم {received}.\n"
            "بعد إرسال جميع مستندات الركاب، من فضلك أرسل *عدد الركاب*.\n\n"
            "🧾 دستاویز نمبر {received} موصول ہو گئی ہے۔\n"
            "جب سب مسافروں کے دستاویزات بھیج دیں، تو براہ کرم *مسافروں کی تعداد* نمبر میں بھیجیں۔"
        )
        msg = msg.replace("{received}", str(received))
        _send_thread_reply(doc, msg)
    else:
        # We know expected passengers but not yet enough docs
        remaining = max(expected - received, 0)
        if remaining > 0:
            msg = (
                f"✅ Document {received}/{expected} received.\n"
                f"Please send the remaining {remaining} document(s).\n\n"
                f"✅ تم استلام المستند رقم {received} من {expected}.\n"
                f"من فضلك أرسل باقي {remaining} مستند(ات).\n\n"
                f"✅ {received}/{expected} دستاویز موصول ہو گئی ہے۔\n"
                f"براہ کرم باقی {remaining} دستاویز بھیج دیں۔"
            )
            _send_thread_reply(doc, msg)
        else:
            # Docs >= expected but route not set yet
            if not getattr(contact, "preferred_route", None):
                _ask_route_choice(doc, contact)
            # no finalize here; it will happen after route selection


# ---------------------------------------------------------------------------
# Driver & Trip helpers
# ---------------------------------------------------------------------------

def _normalize_for_match(value: str) -> str:
    """Keep only digits and compare by last 10 digits."""
    if not value:
        return ""
    digits = re.sub(r"\D", "", value)  # remove everything except 0-9
    # Use last 10 digits (works well for mobile numbers)
    return digits[-10:] if len(digits) >= 10 else digits


def _find_driver_by_phone(phone: str):
    """
    Resolve Staff from WhatsApp number by matching LAST 10 DIGITS only.

    This makes these equivalent:
    +923003764818
    923003764818
    03003764818
    3003764818
    """
    key = _normalize_for_match(phone)

    if not key:
        return None

    # Get all Staff with some mobile_no, then compare in Python
    staff_rows = frappe.get_all(
        "Staff",
        filters={"mobile_no": ["!=", ""]},
        fields=["name", "mobile_no"],
    )

    for row in staff_rows:
        candidate_key = _normalize_for_match(row.get("mobile_no"))
        if candidate_key and candidate_key == key:
            return row["name"]

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
        trip = _create_new_trip_for_driver(driver_name, contact)
        _update_contact_state(contact, current_trip=trip.name)

    return trip


def _create_new_trip_for_driver(driver_name: str, contact=None):
    """Create a new Trip for this driver, using the driver's selected route if available."""
    trip = frappe.new_doc("Trip")
    trip.driver = driver_name

    default_route = None

    # 1) Prefer route chosen by WhatsApp bot
    if contact and getattr(contact, "preferred_route", None):
        default_route = contact.preferred_route

    # 2) Fallback: first available Route
    if not default_route:
        default_route = frappe.db.get_value("Route", {}, "name")

    if default_route:
        trip.trip_route = default_route  # fetch_from on Trip will fill from/to/distance/duration/avg_speed

        # OPTIONAL: if you want to force-copy instead of just relying on fetch_from:
        # route_doc = frappe.get_doc("Route", default_route)
        # trip.from_location = route_doc.from_city
        # trip.to_location = route_doc.to_city
        # trip.distance = route_doc.distance
        # trip.duration = route_doc.duration
        # trip.avg_speed_kmph = route_doc.avg_speed_kmph

    # Basic trip info
    trip.trip_status = "Scheduled"
    trip.date = nowdate()            # Today
    trip.departure = now_datetime()  # Now

    # mobile_no & assigned_vehicle will auto-fetch from driver via fetch_froms
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
    # find File linked to this WhatsApp Message (created via Attach field)
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
    history = frappe.get_doc({
        "doctype": "OCR History",
        # ✅ Match your new Select options
        "source": "WhatsApp Message",
        "ocr_engine": "Hybrid",  # or set dynamically later
        "reference_doctype": "WhatsApp Message",
        "reference_name": message_doc.name,
        "trip": trip.name,
        "file": file_doc,
        # NOTE: we are not using waba_message field anymore
    })
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
        history.json_data = json.dumps({"_raw": str(json_payload)}, ensure_ascii=False)

    history.save(ignore_permissions=True)

    # Consider success only if basic fields exist
    min_conf = 40  # you can tune this later
    if history.full_name and history.id_no and (history.confidence or 0) >= min_conf:
        return True
    
    return False

def _finalize_trip_and_kashf(contact, driver_name: str, trip):
    """
    When expected_passengers == received_images (or more),
    fill Passengers from OCR History and send Trip PDF via WhatsApp.
    Only runs when route already chosen (enforced by _maybe_finalize_trip).
    """
    expected = int(getattr(contact, "expected_passengers", 0) or 0)
    received = int(getattr(contact, "received_images", 0) or 0)

    if expected <= 0 or received <= 0:
        return

    # 0) Apply chosen route to Trip if available
    preferred_route = getattr(contact, "preferred_route", None)
    if preferred_route and trip.trip_route != preferred_route:
        trip.trip_route = preferred_route

    # 1) Get OCR History rows for this Trip
    ocr_rows = frappe.get_all(
        "OCR History",
        filters={"trip": trip.name},
        fields=["name", "full_name", "id_no", "nationality"],
        order_by="creation asc",
    )

    # Only use up to expected rows
    ocr_rows = ocr_rows[:expected]

    # 2) (optional) clear previous passengers if you want a clean rebuild
    # trip.set("passengers", [])

    # 3) Fill Passengers table from OCR
    for row in ocr_rows:
        passenger = trip.append("passengers", {})
        passenger.passenger_name = row.get("full_name") or ""
        passenger.idpassport_no = row.get("id_no") or ""
        passenger.nationality = row.get("nationality") or ""

    trip.save(ignore_permissions=True)
    trip.add_comment(
        "Info",
        f"Passengers auto-filled from WhatsApp OCR at {now_datetime()}."
    )

    # 4) Send Kashf (Trip PDF) via existing function
    try:
        send_trip_pdf_via_whatsapp(trip.name)
    except Exception:
        frappe.log_error("Kashf send failed", f"Trip: {trip.name}")

    # 5) Inform driver
    sender_no = contact.whatsapp_id
    msg = (
        "✅ All passenger documents received, route set, and your Kashf has been prepared and sent.\n"
        "✅ تم استلام جميع مستندات الركاب، وتثبيت خط السير، وتم تجهيز كشف الرحلة وإرساله لك.\n"
        "✅ تمام، سب مسافروں کے دستاویزات اور روٹ سیٹ ہو گیا، آپ کا کشف تیار ہو کر بھیج دیا گیا ہے۔"
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
def _maybe_finalize_trip(contact, driver_name: str, trip) -> bool:
    """
    Check if we have enough info to finalize:
    - expected_passengers is set
    - received_images >= expected_passengers
    - route chosen (preferred_route)
    If yes → call _finalize_trip_and_kashf and return True.
    """
    expected = int(getattr(contact, "expected_passengers", 0) or 0)
    received = int(getattr(contact, "received_images", 0) or 0)
    preferred_route = getattr(contact, "preferred_route", None)

    if expected > 0 and received >= expected and preferred_route:
        _finalize_trip_and_kashf(contact, driver_name, trip)
        return True

    return False


# ---------------------------------------------------------------------------
# WhatsApp send helpers (local)
# ---------------------------------------------------------------------------

def _send_thread_reply(incoming_doc, message: str):
    """Create a reply message (is_reply=1, uses incoming.message_id)."""
    to = normalize_phone(getattr(incoming_doc, "from_", "") or getattr(incoming_doc, "from", "") or "")
    if not to:
        return

    reply = frappe.get_doc({
        "doctype": "WhatsApp Message",
        "type": "Outgoing",
        "to": to,
        "content_type": "text",
        "message": message,
        "message_type": "Manual",
        "is_reply": 1,
        "reply_to_message_id": incoming_doc.message_id,
    })
    reply.insert(ignore_permissions=True)
    return reply.name


def _send_plain_message(to: str, message: str):
    """Non-thread text message (for final Kashf notification)."""
    to = normalize_phone(to)
    if not to:
        return

    msg = frappe.get_doc({
        "doctype": "WhatsApp Message",
        "type": "Outgoing",
        "to": to,
        "content_type": "text",
        "message": message,
        "message_type": "Manual",
    })
    msg.insert(ignore_permissions=True)
    return msg.name
