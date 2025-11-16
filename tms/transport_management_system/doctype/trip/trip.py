# Copyright (c) 2025, Galaxy Labs and contributors
# For license information, please see license.txt

import os
import json
import frappe
import uuid
import qrcode
import base64
from io import BytesIO
from frappe.website.website_generator import WebsiteGenerator
from frappe.utils import getdate, get_url
from hijri_converter import Gregorian

class Trip(WebsiteGenerator):
    def before_insert(self):
        # UUID
        if not self.uuid:
            self.uuid = str(uuid.uuid4())

        # Use UUID as public route
        if not self.route:
            self.route = self.uuid

        # Hijri date
        if self.date and not self.hijri_date:
            g = getdate(self.date)
            h = Gregorian(g.year, g.month, g.day).to_hijri()
            self.hijri_date = f"{h.year:04d}-{h.month:02d}-{h.day:02d}"

    def after_insert(self):
        # Build public URL from site config (respects https and domain)
        if self.route and not self.qr_code:
            base_url = get_url()                 # e.g. https://yourdomain.com
            public_url = f"{base_url.rstrip('/')}/{self.route.lstrip('/')}"
            self.qr_code = self.generate_qr_code(public_url)
            self.db_set("qr_code", self.qr_code)

    def generate_qr_code(self, data: str) -> str:
        qr = qrcode.QRCode(version=1, box_size=10, border=2)
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image()
        buf = BytesIO()
        img.save(buf, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

    # OCR METHODS - Clean Integration
    def init_ocr_manager(self):
        """Initialize OCR manager only when needed"""
        if not hasattr(self, '_ocr_manager'):
            from tms.utils.ocr_manager import OCRManager
            self._ocr_manager = OCRManager()
        return self._ocr_manager
    
    @frappe.whitelist()
    def extract_passengers_tesseract(self, file_urls=None):
        """Extract passengers using Tesseract OCR (offline)"""
        try:
            ocr_manager = self.init_ocr_manager()
            
            if not file_urls:
                # Get all attachments
                files = frappe.get_all(
                    "File",
                    filters={"attached_to_doctype": self.doctype, "attached_to_name": self.name},
                    fields=["file_url"]
                )
                file_urls = [f["file_url"] for f in files]
            
            if isinstance(file_urls, str):
                try:
                    file_urls = json.loads(file_urls)
                except json.JSONDecodeError:
                    # Handle comma-separated string
                    file_urls = [url.strip() for url in file_urls.split(",") if url.strip()]
            
            if not file_urls:
                return {
                    "success": False,
                    "message": "No files found to process",
                    "passengers_added": 0
                }
            
            results = ocr_manager.batch_process(file_urls)
            
            successful_extractions = 0
            for result in results:
                if result.get("success"):
                    data = result["data"]["structured_data"]
                    if data.get("name"):
                        self.append("passengers", {
                            "passenger_name": data.get("name"),
                            "idpassport_no": data.get("id_no", ""),
                            "nationality": data.get("nationality", "")
                        })
                        successful_extractions += 1
            
            if successful_extractions > 0:
                self.save()
                frappe.db.commit()
            
            return {
                "success": True,
                "trip": self.name,
                "passengers_added": successful_extractions,
                "ocr_engine": "tesseract",
                "details": results
            }
            
        except Exception as e:
            frappe.log_error(f"OCR extraction failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "passengers_added": 0
            }

    @frappe.whitelist()
    def add_passenger_from_ocr(self, file_url):
        """Add single passenger from OCR scan"""
        try:
            ocr_manager = self.init_ocr_manager()
            result = ocr_manager.extract_from_image(file_url)
            data = result["structured_data"]
            
            if data.get("name"):
                self.append("passengers", {
                    "passenger_name": data.get("name"),
                    "idpassport_no": data.get("id_no", ""),
                    "nationality": data.get("nationality", ""),
                    "ocr_confidence": data.get("confidence", 0)
                })
                
                self.save(ignore_permissions=True)
                frappe.db.commit()
                
                return {
                    "success": True,
                    "passenger_added": data.get("name"),
                    "confidence": data.get("confidence", 0)
                }
            else:
                return {
                    "success": False,
                    "message": "Could not extract passenger name from image"
                }
                
        except Exception as e:
            frappe.log_error(f"Single OCR extraction failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    @frappe.whitelist()
    def verify_ocr_result(self, passenger_name, verified_data):
        """Verify and correct OCR results for learning"""
        try:
            if isinstance(verified_data, str):
                verified_data = json.loads(verified_data)
            
            ocr_manager = self.init_ocr_manager()
            
            # Find the passenger
            passenger = None
            for p in self.passengers:
                if p.passenger_name == passenger_name:
                    passenger = p
                    break
            
            if passenger:
                # Store original values for learning
                original_data = {
                    "name": passenger.passenger_name,
                    "id_no": passenger.idpassport_no,
                    "nationality": passenger.nationality
                }
                
                # Update with verified data
                passenger.passenger_name = verified_data.get("name", passenger.passenger_name)
                passenger.idpassport_no = verified_data.get("id_no", passenger.idpassport_no)
                passenger.nationality = verified_data.get("nationality", passenger.nationality)
                
                # Learn from correction if values changed
                if original_data != verified_data:
                    ocr_manager.verify_and_learn(passenger_name, verified_data)
                
                self.save()
                frappe.db.commit()
                
                return {
                    "success": True, 
                    "message": "Verified and learned from correction"
                }
            
            return {
                "success": False, 
                "message": "Passenger not found"
            }
            
        except Exception as e:
            frappe.log_error(f"OCR verification failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    @frappe.whitelist()
    def get_ocr_learning_stats(self):
        """Get OCR learning statistics for this trip"""
        try:
            ocr_manager = self.init_ocr_manager()
            return ocr_manager.get_learning_stats()
        except Exception as e:
            frappe.log_error(f"Getting OCR stats failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }


# Remove these duplicate methods from outside the class - they're already inside the class

# Optional: Keep your existing API endpoints for backward compatibility
@frappe.whitelist()
def create_connected_trip(source_trip, route_name, connection_type=None):
    source_doc = frappe.get_doc("Trip", source_trip)
    new_trip = frappe.new_doc("Trip")
    new_trip.driver = source_doc.driver
    new_trip.assigned_vehicle = source_doc.assigned_vehicle
    new_trip.date = frappe.utils.nowdate()
    new_trip.from_route = frappe.get_doc("Route", route_name).from_city
    new_trip.to = frappe.get_doc("Route", route_name).to_city

    new_trip.insert(ignore_permissions=True)
    return new_trip.name

@frappe.whitelist()
def add_passenger_from_ocr(self, file_url):
    """Add single passenger from OCR scan"""
    try:
        ocr_manager = self.init_ocr_manager()
        result = ocr_manager.extract_from_image(file_url)
        data = result["structured_data"]
        
        if data.get("name"):
            self.append("passengers", {
                "passenger_name": data.get("name"),
                "idpassport_no": data.get("id_no", ""),
                "nationality": data.get("nationality", ""),
                "ocr_confidence": data.get("confidence", 0)
            })
            
            self.save(ignore_permissions=True)
            frappe.db.commit()
            
            return {
                "success": True,
                "passenger_added": data.get("name"),
                "confidence": data.get("confidence", 0)
            }
        else:
            return {
                "success": False,
                "message": "Could not extract passenger name from image"
            }
            
    except Exception as e:
        frappe.log_error(f"Single OCR extraction failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }
# import frappe
# import uuid
# import qrcode
# import base64
# from io import BytesIO
# from frappe.website.website_generator import WebsiteGenerator
# from frappe.utils import getdate, get_url
# from hijri_converter import Gregorian

# class Trip(WebsiteGenerator):
#     def before_insert(self):
#         # UUID
#         if not self.uuid:
#             self.uuid = str(uuid.uuid4())

#         # Use UUID as public route
#         if not self.route:
#             self.route = self.uuid

#         # Hijri date
#         if self.date and not self.hijri_date:
#             g = getdate(self.date)
#             h = Gregorian(g.year, g.month, g.day).to_hijri()
#             self.hijri_date = f"{h.year:04d}-{h.month:02d}-{h.day:02d}"

#     def after_insert(self):
#         # Build public URL from site config (respects https and domain)
#         if self.route and not self.qr_code:
#             base_url = get_url()                 # e.g. https://yourdomain.com
#             public_url = f"{base_url.rstrip('/')}/{self.route.lstrip('/')}"
#             self.qr_code = self.generate_qr_code(public_url)
#             self.db_set("qr_code", self.qr_code)

#     def generate_qr_code(self, data: str) -> str:
#         qr = qrcode.QRCode(version=1, box_size=10, border=2)
#         qr.add_data(data)
#         qr.make(fit=True)
#         img = qr.make_image()
#         buf = BytesIO()
#         img.save(buf, format="PNG")
#         return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()




# @frappe.whitelist()
# def create_connected_trip(source_trip, route_name, connection_type=None):
#     source_doc = frappe.get_doc("Trip", source_trip)
#     new_trip = frappe.new_doc("Trip")
#     new_trip.driver = source_doc.driver
#     new_trip.assigned_vehicle = source_doc.assigned_vehicle
#     new_trip.date = frappe.utils.nowdate()
#     new_trip.from_route = frappe.get_doc("Route", route_name).from_city  # corrected name
#     new_trip.to = frappe.get_doc("Route", route_name).to_city     # corrected name

#     new_trip.insert(ignore_permissions=True)
#     return new_trip.name

