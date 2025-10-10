import frappe
from tms.utils.ocr_utils import extract_text_from_file
from tms.utils.parser import parse_passenger_details

@frappe.whitelist(allow_guest=False)
def create_trip_from_ocr(file_url):
    text = extract_text_from_file(file_url)
    passenger = parse_passenger_details(text)

    # match nationality to Country
    country = frappe.db.get_value("Country", {"country_name": passenger.get("nationality")}, "name")

    trip = frappe.new_doc("Trip")
    trip.trip_type = "Umrah"
    trip.travel_date = frappe.utils.nowdate()
    trip.append("passengers", {
        "passenger_name": passenger.get("name"),
        "id_number": passenger.get("id_no"),
        "country": country
    })
    trip.insert(ignore_permissions=True)
    trip.save(ignore_permissions=True)

    frappe.delete_doc_if_exists("File", {"file_url": file_url})  # cleanup
    return {"trip_name": trip.name}
