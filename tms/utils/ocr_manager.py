# tms/utils/ocr_manager.py
import frappe
import json
import os
from pathlib import Path

class OCRManager:
    def __init__(self):
        self.tesseract_ocr = self.init_tesseract_ocr()
        self.ocr_history = []
    
    def init_tesseract_ocr(self):
        """Initialize Tesseract OCR with error handling"""
        try:
            from .enhanced_tesseract_ocr import EnhancedTesseractOCR
            return EnhancedTesseractOCR()
        except Exception as e:
            frappe.log_error(f"Initializing Tesseract OCR failed: {e}")
            raise
    
    def extract_from_image(self, file_url, use_learning=True):
        """Main OCR extraction method"""
        try:
            file_path = self.get_file_path(file_url)
            
            if not os.path.exists(file_path):
                frappe.log_error(f"OCR file not found: {file_path}")
                return {
                    "raw_text": "",
                    "structured_data": {
                        "name": "",
                        "id_no": "",
                        "nationality": "",
                        "confidence": 0
                    },
                    "ocr_engine": "tesseract"
                }
            
            # Extract text using Tesseract
            raw_text = self.tesseract_ocr.extract_text_with_tesseract(file_path)
            
            # Extract structured data
            structured_data = self.tesseract_ocr.extract_structured_data(raw_text)
            
            # Store in history for learning
            if use_learning:
                self.ocr_history.append({
                    "file_url": file_url,
                    "raw_text": raw_text,
                    "extracted_data": structured_data,
                    "timestamp": frappe.utils.now()
                })
            
            return {
                "raw_text": raw_text,
                "structured_data": structured_data,
                "ocr_engine": "tesseract"
            }
        except Exception as e:
            frappe.log_error(f"OCR extraction from image failed: {e}")
            return {
                "raw_text": "",
                "structured_data": {
                    "name": "",
                    "id_no": "",
                    "nationality": "",
                    "confidence": 0
                },
                "ocr_engine": "tesseract"
            }
    
    def get_file_path(self, file_url):
        """Convert file URL to filesystem path"""
        try:
            if file_url.startswith('/private/'):
                return frappe.get_site_path('private', 'files', Path(file_url).name)
            else:
                return frappe.get_site_path('public', 'files', Path(file_url).name)
        except Exception as e:
            frappe.log_error(f"Getting file path failed: {e}")
            return ""
    
    def verify_and_learn(self, ocr_result_id, verified_data):
        """Verify OCR result and learn from corrections"""
        try:
            # Find the OCR result in history
            ocr_entry = None
            for entry in self.ocr_history:
                if entry.get("id") == ocr_result_id:
                    ocr_entry = entry
                    break
            
            if ocr_entry and verified_data:
                # Learn from the verified data
                self.tesseract_ocr.learn_from_verified_data(
                    ocr_entry["raw_text"], 
                    verified_data
                )
                
                # Apply corrections if text differs
                extracted = ocr_entry["extracted_data"]
                if extracted.get("name") != verified_data.get("name"):
                    self.tesseract_ocr.learn_from_correction(
                        extracted.get("name", ""),
                        verified_data.get("name", "")
                    )
        except Exception as e:
            frappe.log_error(f"Verifying and learning from OCR failed: {e}")
    
    def batch_process(self, file_urls):
        """Process multiple files at once"""
        results = []
        for file_url in file_urls:
            try:
                result = self.extract_from_image(file_url)
                results.append({
                    "file_url": file_url,
                    "success": True,
                    "data": result
                })
            except Exception as e:
                results.append({
                    "file_url": file_url,
                    "success": False,
                    "error": str(e)
                })
        
        return results
    
    def get_learning_stats(self):
        """Get learning statistics"""
        try:
            return {
                "name_patterns": len(self.tesseract_ocr.learning_data.get("name_patterns", [])),
                "id_patterns": len(self.tesseract_ocr.learning_data.get("id_patterns", [])),
                "nationality_patterns": len(self.tesseract_ocr.learning_data.get("nationality_patterns", [])),
                "corrections": len(self.tesseract_ocr.learning_data.get("corrections", {})),
                "ocr_history_count": len(self.ocr_history)
            }
        except Exception as e:
            frappe.log_error(f"Getting learning stats failed: {e}")
            return {
                "name_patterns": 0,
                "id_patterns": 0,
                "nationality_patterns": 0,
                "corrections": 0,
                "ocr_history_count": 0
            }