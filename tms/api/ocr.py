# tms/tms/api/ocr.py
import frappe
from frappe.utils import nowdate
from tms.utils.ocr_manager import OCRManager

@frappe.whitelist(allow_guest=False)
def create_trip_from_tesseract_ocr(file_url: str):
    """Create Trip using Tesseract OCR (completely offline)"""
    try:
        ocr_manager = OCRManager()
        
        # Extract data using Tesseract
        result = ocr_manager.extract_from_image(file_url)
        data = result["structured_data"]
        
        if not data.get("name"):
            frappe.throw("Passenger name not detected — please recheck the uploaded image.")
        
        # Match nationality to Country
        country = None
        if data.get("nationality"):
            country = frappe.db.get_value(
                "Country",
                {"country_name": ["like", f"%{data.get('nationality')}%"]},
                "name",
            )
        
        # Create Trip
        trip = frappe.new_doc("Trip")
        trip.driver_name = "Imran Khan"
        trip.route = "Madina - Makkah"
        trip.departure_time = frappe.utils.now_datetime()
        trip.travel_date = nowdate()
        
        # Add passenger
        trip.append("passengers", {
            "passenger_name": data.get("name"),
            "idpassport_no": data.get("id_no"),
            "nationality": country or data.get("nationality"),
            "contact_no": "",
        })
        
        trip.insert(ignore_permissions=True)
        
        # Cleanup file
        frappe.delete_doc_if_exists("File", {"file_url": file_url})
        
        return {
            "trip_name": trip.name,
            "passengers": trip.passengers,
            "ocr_source": "tesseract_offline",
            "confidence": data.get("confidence", 0)
        }
        
    except Exception as e:
        frappe.log_error(f"Tesseract OCR Trip creation failed: {e}")
        raise

@frappe.whitelist(allow_guest=False)
def batch_process_attachments(trip_name):
    """Process all attachments for a trip using Tesseract"""
    trip = frappe.get_doc("Trip", trip_name)
    return trip.extract_passengers_tesseract()

@frappe.whitelist(allow_guest=False)
def get_ocr_learning_stats():
    """Get statistics about OCR learning progress"""
    ocr_manager = OCRManager()
    return {
        "learned_patterns": {
            "name_patterns": len(ocr_manager.tesseract_ocr.learning_data.get("name_patterns", [])),
            "id_patterns": len(ocr_manager.tesseract_ocr.learning_data.get("id_patterns", [])),
            "nationality_patterns": len(ocr_manager.tesseract_ocr.learning_data.get("nationality_patterns", [])),
            "corrections": len(ocr_manager.tesseract_ocr.learning_data.get("corrections", {})),
        },
        "ocr_history_count": len(ocr_manager.ocr_history)
    }