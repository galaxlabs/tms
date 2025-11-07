import frappe
import os
from frappe.utils import get_site_path
from tms.utils.ocr_service import extract_text_unified
from tms.utils.passenger_parser import parse_passenger_details

@frappe.whitelist()
def process_passengers_batch(trip_name, use_openai=False):
    """
    Unified API endpoint to process all trip attachments.
    """
    trip = frappe.get_doc("Trip", trip_name)
    
    # Get all attached files
    files = frappe.get_all(
        "File",
        filters={"attached_to_doctype": "Trip", "attached_to_name": trip_name},
        fields=["file_url", "name"]
    )
    
    if not files:
        return {"success": False, "message": "No files attached"}
    
    # Get API keys from site config
    openai_key = frappe.conf.get('openai_api_key') if use_openai else None
    
    successful = 0
    processing_details = []
    
    for file in files:
        try:
            file_path = get_site_path(file["file_url"].lstrip("/"))
            
            # Use unified OCR service
            ocr_result = extract_text_unified(file_path, use_openai, openai_key)
            
            if ocr_result and ocr_result['text']:
                # Parse the extracted text
                passenger_data = parse_passenger_details(ocr_result)
                
                if passenger_data and passenger_data.get("name"):
                    # Map nationality to country
                    nationality = passenger_data.get("nationality", "")
                    country_code = None
                    if nationality:
                        country_code = frappe.db.get_value(
                            "Country",
                            {"country_name": ["like", f"%{nationality}%"]},
                            "name"
                        )
                    
                    # Add to child table - Frappe pattern
                    trip.append("passengers", {
                        "passenger_name": passenger_data.get("name"),
                        "idpassport_no": passenger_data.get("id_no", ""),
                        "nationality": country_code or nationality,
                    })
                    
                    successful += 1  # ✅ FIXED: Complete this line
                    processing_details.append({
                        "file": file["file_url"],
                        "status": "success", 
                        "engine": ocr_result['engine'],
                        "passenger": passenger_data.get("name")
                    })
                else:
                    processing_details.append({
                        "file": file["file_url"],
                        "status": "failed", 
                        "reason": "No passenger data extracted",
                        "engine": ocr_result['engine']
                    })
            else:
                processing_details.append({
                    "file": file["file_url"],
                    "status": "failed", 
                    "reason": "No text extracted from image",
                    "engine": "none"
                })
                
        except Exception as e:  # ✅ FIXED: Add missing except block
            frappe.log_error(f"Failed processing {file['file_url']}: {str(e)}")
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
        "message": f"Processed {len(files)} files, added {successful} passengers",
        "passengers_added": successful,
        "details": processing_details
    }


@frappe.whitelist()
def debug_single_file(file_url):
    """
    Debug OCR on a single file
    """
    try:
        file_path = get_site_path(file_url.lstrip("/"))
        
        if not os.path.exists(file_path):
            return {"success": False, "error": "File not found on server"}
        
        # Use free OCR only for debugging
        ocr_result = extract_text_unified(file_path, use_openai=False, openai_key=None)
        
        if ocr_result and ocr_result.get('text'):
            passenger_data = parse_passenger_details(ocr_result)
            
            # Format lines for display
            lines = ocr_result['text'].split('\n')
            formatted_lines = []
            for i, line in enumerate(lines):
                if line.strip():
                    formatted_lines.append(f"Line {i}: {line.strip()}")
            
            return {
                "success": True,
                "ocr_engine": ocr_result.get('engine', 'unknown'),
                "full_text": ocr_result['text'],
                "formatted_lines": formatted_lines,
                "passenger_data": passenger_data,
                "text_length": len(ocr_result['text']),
                "file": file_url
            }
        else:
            return {
                "success": False,
                "error": "No text extracted from image",
                "ocr_engine": "none",
                "file": file_url
            }
            
    except Exception as e:
        frappe.log_error(f"Debug failed: {str(e)}")
        return {"success": False, "error": str(e)}
        