# Copyright (c) 2025, Galaxy Labs and contributors
# For license information, please see license.txt

import json
import frappe
import uuid
import pyqrcode as qrcode
import re  
from frappe.website.website_generator import WebsiteGenerator
from frappe.model.naming import make_autoname
from frappe.utils import getdate, get_url, add_to_date, flt, cint  # 👈 extend this line
from hijri_converter import Gregorian

class Trip(WebsiteGenerator):
    def autoname(self):
        self.name = make_autoname("CELTCO-.YYYY.-.MM.-.####")

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
    
    def validate(self):
        invoice_customers = [row for row in (self.passengers or []) if cint(row.get("is_invoice_customer"))]
        if len(invoice_customers) > 1:
            frappe.throw("Only one passenger can be selected as invoice customer.")

        self.driver_commission_amount = flt(self.trip_value) * flt(self.driver_commission_rate) / 100

        if self.departure and self.duration_minutes:
            self.arrival = add_to_date(self.departure, minutes=int(self.duration_minutes), as_datetime=True)
        else:
            # keep any other validate logic here later
            self.set_estimated_arrival()
    
    def set_estimated_arrival(self):
        """
        Use trip.duration (string) to calculate trip.arrival from trip.departure.
        """
        if not (self.departure and self.duration):
            return

        minutes = self._duration_to_minutes(self.duration)
        if not minutes:
            return

        self.arrival = add_to_date(self.departure, minutes=minutes, as_datetime=True)

    def _duration_to_minutes(self, duration):
        """
        Supported examples for duration:
        - '4:30'
        - '4 hours 30 mins'
        - '4 hr 30 min'
        - '4h 30m'
        - '4.5'  (treated as hours)
        - '4'    (treated as hours)
        """
        if not duration:
            return 0

        s = str(duration).strip().lower()

        # Case 1: HH:MM format
        if ":" in s:
            parts = s.split(":")
            hours = cint(parts[0] or 0)
            mins = cint(parts[1] or 0) if len(parts) > 1 else 0
            return hours * 60 + mins

        # Case 2: 'X hours Y mins', 'X hr Y min', 'Xh Ym', etc.
        hours = 0
        mins = 0

        m = re.search(r"(\d+)\s*(hour|hours|hr|hrs|h)", s)
        if m:
            hours = cint(m.group(1))

        m = re.search(r"(\d+)\s*(minute|minutes|min|mins|m)", s)
        if m:
            mins = cint(m.group(1))

        if hours or mins:
            return hours * 60 + mins

        # Case 3: pure number -> treat as hours
        val = flt(s)
        if val:
            return int(round(val * 60))

        return 0

        # Build public URL from site config (respects https and domain)
    def generate_qr_code(self, data: str) -> str:
        """
        Generate QR code as PNG base64 (data URI) using PyQRCode.
        No PIL needed.
        """
        qr = qrcode.create(data)  # pyqrcode
        png_bytes = qr.png_as_base64_str(scale=6)  # scale controls size
        return "data:image/png;base64," + png_bytes

    # def generate_qr_code(self, data: str) -> str:
    #     qr = qrcode.QRCode(version=1, box_size=10, border=2)
    #     qr.add_data(data)
    #     qr.make(fit=True)
    #     img = qr.make_image()
    #     buf = BytesIO()
    #     img.save(buf, format="PNG")
    #     return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

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
                            "document_number": data.get("id_no") or data.get("document_number") or "",
                            "contact_no": data.get("mobile_no") or data.get("contact_no") or "",
                            "nationality": data.get("nationality") or "",
                            "document_type": data.get("document_type") or "Passport",
                            "source": "OCR",
                            "is_auto_filled": 1
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
                    "document_number": data.get("id_no") or data.get("document_number") or "",
                    "contact_no": data.get("mobile_no") or data.get("contact_no") or "",
                    "nationality": data.get("nationality") or "",
                    "document_type": data.get("document_type") or "Passport",
                    "source": "OCR",
                    "is_auto_filled": 1
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
                    "document_number": passenger.document_number,
                    "contact_no": passenger.contact_no,
                    "nationality": passenger.nationality,
                    "document_type": passenger.document_type
                }
                
                # Update with verified data
                passenger.passenger_name = verified_data.get("name", passenger.passenger_name)
                passenger.document_number = verified_data.get("document_number") or verified_data.get("id_no") or passenger.document_number
                passenger.contact_no = verified_data.get("contact_no") or verified_data.get("mobile_no") or passenger.contact_no
                passenger.nationality = verified_data.get("nationality", passenger.nationality)
                passenger.document_type = verified_data.get("document_type", passenger.document_type)
                
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
