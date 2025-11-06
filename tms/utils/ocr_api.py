import frappe
import os
import re
from frappe.utils import get_site_path
from .ocr_space_service import extract_text_via_ocrspace_with_fallback

def parse_passenger_details(ocr_text):
    """
    Enhanced parser that specifically extracts ONLY name, ID, nationality
    and ignores all other text from the document
    """
    # Clean the text
    text = ' '.join(ocr_text.split())
    
    result = {}
    
    # Enhanced name patterns - more specific to avoid capturing entire document
    name_patterns = [
        # Look for name after specific labels (more restrictive)
        r'(?:Name|اسم)[\s:]*([A-Za-z\u0600-\u06FF]{2,}(?:\s+[A-Za-z\u0600-\u06FF]{2,}){1,3})',
        r'(?:Full Name|الاسم الكامل)[\s:]*([A-Za-z\u0600-\u06FF]{2,}(?:\s+[A-Za-z\u0600-\u06FF]{2,}){1,3})',
        r'(?:Passenger Name|اسم المسافر)[\s:]*([A-Za-z\u0600-\u06FF]{2,}(?:\s+[A-Za-z\u0600-\u06FF]{2,}){1,3})',
        r'(?:Holder\'s Name|اسم الحامل)[\s:]*([A-Za-z\u0600-\u06FF]{2,}(?:\s+[A-Za-z\u0600-\u06FF]{2,}){1,3})',
        # Look for typical name format (2-4 words, title case)
        r'([A-Z][a-z]+ [A-Z][a-z]+(?: [A-Z][a-z]+){0,2})',
    ]
    
    # Enhanced ID patterns
    id_patterns = [
        r'(?:ID|رقم|Passport|جواز)[\s:]*([A-Z0-9]{6,12})',
        r'(?:Identity Card|بطاقة الهوية)[\s:]*([A-Z0-9]{6,12})',
        r'(?:Number|الرقم)[\s:]*([A-Z0-9]{6,12})',
        r'([A-Z][0-9]{7,10})',  # Common passport format
        r'(\d{9,12})',  # Numeric IDs
    ]
    
    # Enhanced nationality patterns
    nationality_patterns = [
        r'(?:Nationality|جنسية)[\s:]*([A-Za-z\u0600-\u06FF]{2,20})',
        r'(?:Country|بلد)[\s:]*([A-Za-z\u0600-\u06FF]{2,20})',
        r'(?:Citizenship|مواطنة)[\s:]*([A-Za-z\u0600-\u06FF]{2,20})',
    ]
    
    # Extract name with better validation
    extracted_name = None
    for pattern in name_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            candidate_name = match.group(1).strip()
            # Validate that this looks like a real name (not document text)
            if is_valid_name(candidate_name):
                extracted_name = candidate_name
                break
    
    # Extract ID
    extracted_id = None
    for pattern in id_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            extracted_id = match.group(1).strip()
            break
    
    # Extract nationality
    extracted_nationality = None
    for pattern in nationality_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            extracted_nationality = match.group(1).strip()
            break
    
    # Only return valid data
    if extracted_name:
        result["name"] = extracted_name[:140]  # Ensure it fits in the field
    if extracted_id:
        result["id_no"] = extracted_id
    if extracted_nationality:
        result["nationality"] = extracted_nationality
    
    return result

def is_valid_name(name_candidate):
    """
    Validate that the extracted text is actually a name and not document text
    """
    if not name_candidate or len(name_candidate) < 2:
        return False
    
    # Common document phrases that might be mistakenly captured as names
    invalid_phrases = [
        'islamic republic', 'president', 'director', 'general', 
        'immigration', 'passports', 'bearer', 'assistance',
        'protection', 'necessary', 'freely', 'hindrance',
        'concern', 'republic of', 'all those', 'whom it may',
        'allow the', 'without let', 'afford the', 'as may be',
        'to whom', 'it may concern', 'pass freely'
    ]
    
    name_lower = name_candidate.lower()
    
    # Check if it contains invalid document phrases
    for phrase in invalid_phrases:
        if phrase in name_lower:
            return False
    
    # Check if it's too long to be a reasonable name
    if len(name_candidate) > 50:
        return False
    
    # Check if it has typical name structure (2-4 words)
    words = name_candidate.split()
    if len(words) < 1 or len(words) > 4:
        return False
    
    # Check that words are reasonable length for names
    for word in words:
        if len(word) < 2 or len(word) > 15:
            return False
    
    return True

def debug_ocr_text(extracted_text, file_url):
    """
    Debug function to see what OCR is actually extracting
    """
    frappe.logger().info(f"🔍 OCR DEBUG for {file_url}:")
    frappe.logger().info(f"Full text length: {len(extracted_text)}")
    frappe.logger().info(f"First 500 chars: {extracted_text[:500]}")
    
    # Try to find any potential name-like patterns
    lines = extracted_text.split('\n')
    for i, line in enumerate(lines):
        if len(line.strip()) > 10:  # Non-empty lines
            frappe.logger().info(f"Line {i}: {line.strip()}")
    
    return len(extracted_text)

@frappe.whitelist()
def process_passengers_with_ocrspace(trip_name):
    """
    Main function with enhanced parsing and debugging
    """
    trip = frappe.get_doc("Trip", trip_name)
    
    # Get files
    files = frappe.get_all(
        "File",
        filters={"attached_to_doctype": "Trip", "attached_to_name": trip_name},
        fields=["file_url", "name"]
    )

    if not files:
        return {"success": False, "message": "❌ No files attached to this Trip."}

    # Get API key
    api_key = frappe.conf.get('ocr_space_api_key') or 'helloworld'

    successful = 0
    processing_details = []

    for file in files:
        try:
            file_path = get_site_path(file["file_url"].lstrip("/"))
            
            if not os.path.exists(file_path):
                processing_details.append({
                    "file": file["file_url"], 
                    "status": "error", 
                    "reason": "File not found on server"
                })
                continue
            
            # Extract text with fallback
            extracted_text, ocr_engine = extract_text_via_ocrspace_with_fallback(file_path, api_key)
            
            if extracted_text:
                # Debug: log what we're getting
                text_length = debug_ocr_text(extracted_text, file["file_url"])
                
                # Parse the extracted text with enhanced parser
                passenger_data = parse_passenger_details(extracted_text)
                
                frappe.logger().info(f"Parsed passenger data: {passenger_data}")
                
                if passenger_data and passenger_data.get("name"):
                    # Ensure name is not too long
                    passenger_name = passenger_data.get("name")
                    if len(passenger_name) > 140:
                        passenger_name = passenger_name[:140]
                        frappe.logger().warning(f"Truncated long name to: {passenger_name}")
                    
                    # Map nationality to country
                    nationality = passenger_data.get("nationality", "")
                    country_code = None
                    if nationality:
                        country_code = frappe.db.get_value(
                            "Country",
                            {"country_name": ["like", f"%{nationality}%"]},
                            "name"
                        )
                    
                    # Add to passengers table
                    trip.append("passengers", {
                        "passenger_name": passenger_name,
                        "idpassport_no": passenger_data.get("id_no", ""),
                        "nationality": country_code or nationality,
                    })
                    successful += 1
                    processing_details.append({
                        "file": file["file_url"], 
                        "status": "success", 
                        "passenger_name": passenger_name,
                        "ocr_engine": ocr_engine,
                        "text_length": text_length
                    })
                else:
                    processing_details.append({
                        "file": file["file_url"], 
                        "status": "failed - no passenger data", 
                        "reason": "Could not extract valid name from text",
                        "ocr_engine": ocr_engine,
                        "text_length": text_length,
                        "text_preview": extracted_text[:300]  # First 300 chars for debugging
                    })
            else:
                processing_details.append({
                    "file": file["file_url"], 
                    "status": "failed - no text extracted", 
                    "reason": "Both OCR.space and Tesseract failed",
                    "ocr_engine": "none"
                })

        except Exception as e:
            frappe.log_error(f"Failed to process {file['file_url']}: {str(e)}", "OCR Processing")
            processing_details.append({
                "file": file["file_url"], 
                "status": "error", 
                "reason": str(e)
            })
            continue

    # Save results
    if successful > 0:
        trip.save(ignore_permissions=True)
        frappe.db.commit()

    return {
        "success": successful > 0,
        "message": f"✅ Processed {len(files)} file(s). Added {successful} passenger(s)." if successful > 0 else f"❌ Failed to process {len(files)} file(s).",
        "passengers_added": successful,
        "total_files": len(files),
        "processing_details": processing_details
    }

@frappe.whitelist()
def debug_single_file(file_url):
    """
    Detailed debugging for a single file
    """
    try:
        file_path = get_site_path(file_url.lstrip("/"))
        api_key = frappe.conf.get('ocr_space_api_key') or 'helloworld'
        
        extracted_text, ocr_engine = extract_text_via_ocrspace_with_fallback(file_path, api_key)
        
        if extracted_text:
            # Show full text for analysis
            lines = extracted_text.split('\n')
            formatted_lines = []
            for i, line in enumerate(lines):
                if line.strip():  # Only non-empty lines
                    formatted_lines.append(f"Line {i}: {line.strip()}")
            
            passenger_data = parse_passenger_details(extracted_text)
            
            return {
                "success": True,
                "ocr_engine": ocr_engine,
                "full_text": extracted_text,
                "formatted_lines": formatted_lines,
                "passenger_data": passenger_data,
                "text_length": len(extracted_text),
                "file": file_url
            }
        else:
            return {
                "success": False,
                "error": "No text extracted from image",
                "ocr_engine": ocr_engine,
                "file": file_url
            }
            
    except Exception as e:
        frappe.log_error(f"Debug failed: {str(e)}", "OCR Debug")
        return {"success": False, "error": str(e)}