import frappe, requests, io
from PIL import Image
import pytesseract
from tms.utils.parser import parse_passenger_details

@frappe.whitelist(allow_guest=True)
def webhook():
    try:
        raw = frappe.request.data
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8")
        payload = frappe.parse_json(raw or "{}")
    except Exception:
        payload = {}

    settings = frappe.get_single("Green API")

    sender = (payload.get("senderData") or {}).get("chatId")  # e.g. 923003764818@c.us
    number = sender.split("@")[0] if sender else None

    # Step 1: Sender validation
    if not is_registered_sender(number):
        send_msg(sender, "❌ Access denied. Only registered staff or drivers can use this bot.")
        frappe.log_error(f"Unauthorized attempt from {number}", "Green API Bot")
        return "unauthorized"

    msg = payload.get("messageData", {})
    msg_type = msg.get("typeMessage")

    # Step 2: Only accept image messages
    if msg_type != "imageMessage":
        send_msg(sender, "📄 Please send an ID or passport image.")
        return "no image"

    # Step 3: Download image and extract text
    image_url = msg.get("downloadUrl")
    if not image_url:
        send_msg(sender, "⚠️ Could not get image. Try again.")
        return "no image url"

    img_bytes = requests.get(image_url).content
    image = Image.open(io.BytesIO(img_bytes))
    text = pytesseract.image_to_string(image, lang=settings.language or "eng+ara")

    passenger = parse_passenger_details(text)
    if not passenger.get("name") or not passenger.get("id_no"):
        send_msg(sender, "⚠️ Could not read Name or ID. Please resend a clearer image.")
        return "fail"

    # Step 4: Create Trip
    result = create_trip_for_sender(number, passenger)
    send_msg(sender, f"✅ Trip {result['trip_name']} created for {passenger['name']} ({passenger.get('nationality','')}).")

    return "ok"


def is_registered_sender(number):
    """Check if sender number exists in Employee or Driver"""
    if not number:
        return False
    emp = frappe.db.exists("Staff", {"mobile_no": ["like", f"%{number}%"]})
    drv = frappe.db.exists("Driver", {"cell_number": ["like", f"%{number}%"]})
    return True if emp or drv else False


def create_trip_for_sender(number, passenger):
    """Create a Trip document for sender"""
    trip = frappe.new_doc("Trip")
    trip.travel_date = frappe.utils.nowdate()

    country = frappe.db.get_value("Country", {"country_name": passenger.get("nationality")}, "name")

    trip.append("passengers", {
        "passenger_name": passenger.get("name"),
        "id_number": passenger.get("id_no"),
        "country": country
    })

    # Link to Employee or Driver
    if frappe.db.exists("Staff", {"mobile_no": ["like", f"%{number}%"]}):
        trip.employee = frappe.db.get_value("Staff", {"mobile_no": ["like", f"%{number}%"]}, "name")
    elif frappe.db.exists("Driver", {"cell_number": ["like", f"%{number}%"]}):
        trip.driver = frappe.db.get_value("Driver", {"cell_number": ["like", f"%{number}%"]}, "name")

    trip.insert(ignore_permissions=True)
    return {"trip_name": trip.name}


def send_msg(chat_id, message):
    """Send WhatsApp message via Green API"""
    settings = frappe.get_single("Green API")
    url = f"{settings.api_url}/waInstance{settings.id_instance}/sendMessage/{settings.api_token}"
    requests.post(url, json={"chatId": chat_id, "message": message})
