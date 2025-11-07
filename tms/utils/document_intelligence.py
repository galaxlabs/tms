import re
import frappe
import json
from datetime import datetime

class DocumentIntelligence:
    def __init__(self):
        self.learned_patterns = self._load_learned_patterns()
        self.international_patterns = self._get_international_patterns()
    
    def _load_learned_patterns(self):
        """Load learned patterns from database"""
        try:
            patterns_json = frappe.db.get_value('OCR Learning Patterns', 'main', 'patterns_json')
            if patterns_json:
                return json.loads(patterns_json)
        except:
            pass
        return {}
    
    def _save_learned_patterns(self):
        """Save learned patterns to database"""
        try:
            if not frappe.db.exists('OCR Learning Patterns', 'main'):
                doc = frappe.new_doc('OCR Learning Patterns')
                doc.name = 'main'
            else:
                doc = frappe.get_doc('OCR Learning Patterns', 'main')
            
            doc.patterns_json = json.dumps(self.learned_patterns, indent=2)
            doc.last_updated = datetime.now()
            doc.save(ignore_permissions=True)
            frappe.db.commit()
        except Exception as e:
            frappe.log_error(f"Failed to save patterns: {str(e)}")
    
    def _get_international_patterns(self):
        """International document patterns for global passports/visas"""
        return {
            'saudi_iqama': {
                'name_arabic': [r'([\u0600-\u06FF\s]{3,})'],
                'name_english': [r'([A-Z][A-Z\s]{3,})'],
                'id_number': [r'رقم الهوية\s*(\d{4}/\d{2}/\d{2})', r'ID NO[:\s]*(\d+/\d+/\d+)'],
                'birth_date': [r'تاريخ الميلاد\s*(\d{4}/\d{2}/\d{2})'],
                'nationality': [r'الجنسية\s*([\u0600-\u06FF]+)', r'NATIONALITY[:\s]*([A-Z]+)']
            },
            'saudi_visa': {
                'name': [r'Name\s*([A-Z\s]+)', r'الاسم\s*([A-Z\s]+)'],
                'passport_no': [r'Passport No[.\s]*([A-Z0-9]+)', r'رقم الجواز\s*([A-Z0-9]+)'],
                'nationality': [r'Nationality\s*([A-Z\s]+)', r'الجنسية\s*([\u0600-\u06FF\s]+)'],
                'visa_no': [r'Visa No[.\s]*(\d+)', r'رقم التأشيرة\s*(\d+)'],
                'birth_date': [r'Birth Date\s*(\d{2}/\d{2}/\d{4})']
            },
            'pakistani_passport': {
                'name': [r'([A-Z<]+[A-Z])', r'Surname[:\s]*([A-Z]+)', r'Given Names[:\s]*([A-Z\s]+)'],
                'passport_no': [r'([A-Z]{1,2}\d{7,8})'],
                'nationality': [r'PAKISTAN', r'PAK'],
                'mrz_line2': [r'\d{7,8}[A-Z]<[A-Z<]+\d']  # Machine Readable Zone
            },
            'international_passport': {
                'name': [r'^[A-Z<]{2,40}$', r'Surname[:\s]*([A-Z]+)', r'Given Names[:\s]*([A-Z\s]+)'],
                'passport_no': [r'[A-Z]{1,2}[0-9]{6,8}', r'P<[A-Z<]+'],
                'nationality': [r'[A-Z]{3}'],
                'mrz': [r'P<[A-Z<]+', r'[A-Z]{3}[A-Z<]+']  # Generic MRZ patterns
            },
            'visa_document': {
                'name': [r'Name[:\s]*([A-Z\s]+)', r'الاسم[:\s]*([A-Z\s]+)'],
                'passport_no': [r'Passport[:\s]*([A-Z0-9]+)', r'رقم الجواز[:\s]*([A-Z0-9]+)'],
                'nationality': [r'Nationality[:\s]*([A-Z]+)', r'الجنسية[:\s]*([\u0600-\u06FF]+)'],
                'visa_no': [r'Visa[:\s]*([A-Z0-9]+)']
            }
        }
    
    def detect_document_type(self, ocr_text):
        """Intelligently detect document type with confidence scoring"""
        text_upper = ocr_text.upper()
        text_lines = ocr_text.split('\n')
        
        scores = {}
        
        # Check for Saudi Iqama patterns (from your sample)
        if any('هوية مقيم' in line for line in text_lines) or any('رقم الهوية' in line for line in text_lines):
            scores['saudi_iqama'] = 95
        
        # Check for Saudi Visa patterns (from your sample)
        if any('Visa No.' in line for line in text_lines) or any('رقم التأشيرة' in ocr_text):
            scores['saudi_visa'] = 90
        
        # Check for Pakistani Passport patterns
        if 'ISLAMIC REPUBLIC OF PAKISTAN' in text_upper or 'GOVERNMENT OF PAKISTAN' in text_upper:
            scores['pakistani_passport'] = 85
        
        # Check for international passport patterns
        if any('P<' in line for line in text_lines) or any(re.search(r'[A-Z]{2}\d{7}', line) for line in text_lines):
            scores['international_passport'] = 80
        
        # Check for generic visa patterns
        if any('VISA' in line for line in text_lines) or any('تأشيرة' in line for line in text_lines):
            scores['visa_document'] = 75
        
        # Return highest confidence type
        if scores:
            best_type = max(scores, key=scores.get)
            frappe.logger().info(f"🎯 Detected: {best_type} (confidence: {scores[best_type]}%)")
            return best_type
        
        # Learn new pattern if unknown
        return self._learn_new_pattern(ocr_text)
    
    def _learn_new_pattern(self, ocr_text):
        """Learn patterns from new document types"""
        text_lines = [line.strip() for line in ocr_text.split('\n') if line.strip()]
        
        # Analyze text structure to learn new patterns
        new_pattern = {
            'key_phrases': text_lines[:5],  # First 5 lines as identifying features
            'learned_date': datetime.now().isoformat(),
            'confidence': 50  # Initial low confidence
        }
        
        doc_type = f"learned_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.learned_patterns[doc_type] = new_pattern
        self._save_learned_patterns()
        
        frappe.logger().info(f"🧠 Learned new document type: {doc_type}")
        return doc_type
    
    def extract_fields_intelligent(self, ocr_text, doc_type=None):
        """Extract fields using intelligent pattern matching"""
        if not doc_type:
            doc_type = self.detect_document_type(ocr_text)
        
        extraction_rules = self.international_patterns.get(doc_type, {})
        
        result = {
            'document_type': doc_type,
            'name': self._extract_name_intelligent(ocr_text, doc_type, extraction_rules),
            'id_no': self._extract_id_intelligent(ocr_text, doc_type, extraction_rules),
            'nationality': self._extract_nationality_intelligent(ocr_text, doc_type, extraction_rules),
            'confidence': 80  # Base confidence
        }
        
        # Improve extraction based on learned patterns
        result = self._apply_learned_patterns(ocr_text, result)
        
        return result
    
    def _extract_name_intelligent(self, text, doc_type, rules):
        """Intelligent name extraction based on document type"""
        lines = text.split('\n')
        
        if doc_type == 'saudi_iqama':
            # Extract from your Iqama sample: "MOHAMMAD SHOHEL DULAL MIAH"
            for line in lines:
                if re.match(r'^[A-Z][A-Z\s]{5,}$', line.strip()) and not any(word in line.upper() for word in ['PASSPORT', 'VISA', 'ID']):
                    return line.strip().title()
        
        elif doc_type == 'saudi_visa':
            # Extract from your Visa sample: "AHMED ALI"
            for line in lines:
                if 'Name' in line or 'الاسم' in line:
                    name = self._extract_after_label(line, ['Name', 'الاسم'])
                    if name:
                        return name.strip().title()
        
        elif doc_type == 'pakistani_passport':
            # Extract from MRZ line: "P<PAKMAJEED<<NAZIA<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<"
            for line in lines:
                if line.startswith('P<'):
                    # MRZ format: P<COUNTRY<SURNAME<<GIVENNAMES
                    parts = line.split('<')
                    if len(parts) >= 3:
                        surname = parts[2].replace('<', ' ').strip()
                        given_names = parts[3].replace('<', ' ').strip() if len(parts) > 3 else ''
                        return f"{surname} {given_names}".strip().title()
        
        # Fallback: Look for any name-like patterns
        return self._extract_fallback_name(text)
    
    def _extract_id_intelligent(self, text, doc_type, rules):
        """Intelligent ID/Passport number extraction"""
        lines = text.split('\n')
        
        if doc_type == 'saudi_iqama':
            # Extract from your sample: "رقم الهوية 2025/08/24"
            for line in lines:
                if 'رقم الهوية' in line:
                    id_match = re.search(r'رقم الهوية\s*(\d{4}/\d{2}/\d{2})', line)
                    if id_match:
                        return id_match.group(1)
        
        elif doc_type == 'saudi_visa':
            # Extract from your sample: "Passport No. FY1836741"
            for line in lines:
                if 'Passport No' in line:
                    passport_match = re.search(r'Passport No[.\s]*([A-Z0-9]+)', line)
                    if passport_match:
                        return passport_match.group(1)
        
        elif doc_type in ['pakistani_passport', 'international_passport']:
            # Extract from MRZ or visible number
            for line in lines:
                # MRZ format: CM05714924PAK8902188F28102493110160491492<72
                mrz_match = re.search(r'([A-Z]{1,2}\d{7,8})', line)
                if mrz_match:
                    return mrz_match.group(1)
        
        # Fallback: Look for common ID patterns
        return self._extract_fallback_id(text)
    
    def _extract_nationality_intelligent(self, text, doc_type, rules):
        """Intelligent nationality extraction"""
        lines = text.split('\n')
        
        if doc_type == 'saudi_visa':
            # Extract from your sample: "Nationality Pakistan"
            for line in lines:
                if 'Nationality' in line:
                    nationality = self._extract_after_label(line, ['Nationality'])
                    if nationality:
                        return nationality.strip().title()
        
        elif doc_type == 'pakistani_passport':
            return 'Pakistan'  # Explicit for Pakistani passports
        
        # Fallback: Look for country names
        countries = ['PAKISTAN', 'SAUDI ARABIA', 'INDIA', 'BANGLADESH', 'EGYPT', 'USA', 'UK']
        for line in lines:
            for country in countries:
                if country in line.upper():
                    return country.title()
        
        return None
    
    def _extract_fallback_name(self, text):
        """Fallback name extraction using multiple strategies"""
        lines = text.split('\n')
        
        # Strategy 1: Look for all-caps lines that look like names
        for line in lines:
            clean_line = line.strip()
            if (re.match(r'^[A-Z][A-Z\s]{3,30}$', clean_line) and 
                not any(word in clean_line.upper() for word in ['PASSPORT', 'VISA', 'ID', 'CARD', 'REPUBLIC'])):
                return clean_line.title()
        
        # Strategy 2: Look for name labels
        for line in lines:
            name = self._extract_after_label(line, ['Name', 'اسم', 'الاسم'])
            if name and self._is_valid_name(name):
                return name.title()
        
        return None
    
    def _extract_fallback_id(self, text):
        """Fallback ID extraction using multiple strategies"""
        # Look for common ID patterns
        patterns = [
            r'[A-Z]{1,2}\d{7,8}',  # Passport numbers
            r'\d{4}/\d{2}/\d{2}',   # Date-like IDs
            r'[A-Z0-9]{6,12}',      # Generic IDs
            r'\d{9,14}'             # Long numeric IDs
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                if self._is_valid_id(match):
                    return match
        
        return None
    
    def _extract_after_label(self, line, labels):
        """Extract value after labels"""
        for label in labels:
            pattern = rf'{label}[\s:\-]*([^\n\r<>]*)'
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                return value if value else None
        return None
    
    def _is_valid_name(self, name):
        """Validate name"""
        if not name or len(name) < 2 or len(name) > 50:
            return False
        invalid = ['PASSPORT', 'VISA', 'ID', 'CARD', 'REPUBLIC', 'GOVERNMENT']
        return not any(word in name.upper() for word in invalid)
    
    def _is_valid_id(self, id_no):
        """Validate ID"""
        if not id_no or len(id_no) < 5:
            return False
        return any(c.isalnum() for c in id_no)
    
    def _apply_learned_patterns(self, ocr_text, result):
        """Apply learned patterns to improve extraction"""
        # This would use the self.learned_patterns to refine results
        # For now, return as-is - will be enhanced with more learning data
        return result