import frappe
from .document_intelligence import DocumentIntelligence

class SmartFieldExtractor:
    def __init__(self):
        self.intelligence = DocumentIntelligence()
        self.extraction_history = []
    
    def extract_fields(self, ocr_text, doc_type=None):
        """
        Extract fields using intelligent document understanding
        """
        try:
            # Use document intelligence for smart extraction
            result = self.intelligence.extract_fields_intelligent(ocr_text, doc_type)
            
            # Log successful extraction for learning
            if result.get('name'):
                self._log_extraction(ocr_text, result)
            
            frappe.logger().info(f"🧠 Intelligent extraction: {result}")
            return result
            
        except Exception as e:
            frappe.log_error(f"Intelligent extraction failed: {str(e)}")
            # Fallback to basic extraction
            return self._fallback_extraction(ocr_text)
    
    def _log_extraction(self, ocr_text, result):
        """Log successful extractions for continuous learning"""
        try:
            # Store in extraction history (could be saved to DB)
            extraction_record = {
                'timestamp': frappe.utils.now(),
                'document_type': result.get('document_type'),
                'extracted_data': result,
                'text_sample': ocr_text[:500]  # First 500 chars for pattern learning
            }
            
            self.extraction_history.append(extraction_record)
            
            # Keep only recent history
            if len(self.extraction_history) > 100:
                self.extraction_history.pop(0)
                
        except Exception as e:
            frappe.log_error(f"Failed to log extraction: {str(e)}")
    
    def _fallback_extraction(self, ocr_text):
        """Fallback extraction when intelligent method fails"""
        # Your existing basic extraction logic
        import re
        
        result = {
            'document_type': 'unknown',
            'name': None,
            'id_no': None,
            'nationality': None
        }
        
        # Basic patterns as fallback
        name_patterns = [r'Name[:\s]*([A-Z\s]{3,})', r'الاسم[:\s]*([\u0600-\u06FF\s]{3,})']
        id_patterns = [r'Passport[:\s]*([A-Z0-9]{6,12})', r'رقم[:\s]*([A-Z0-9]{6,12})']
        nationality_patterns = [r'Nationality[:\s]*([A-Z\s]+)', r'الجنسية[:\s]*([\u0600-\u06FF\s]+)']
        
        for pattern in name_patterns:
            match = re.search(pattern, ocr_text, re.IGNORECASE)
            if match:
                result['name'] = match.group(1).strip().title()
                break
        
        for pattern in id_patterns:
            match = re.search(pattern, ocr_text, re.IGNORECASE)
            if match:
                result['id_no'] = match.group(1).strip()
                break
        
        for pattern in nationality_patterns:
            match = re.search(pattern, ocr_text, re.IGNORECASE)
            if match:
                result['nationality'] = match.group(1).strip().title()
                break
        
        return result