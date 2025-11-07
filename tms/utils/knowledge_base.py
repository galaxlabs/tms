import frappe
import json
import hashlib
from datetime import datetime

class DocumentKnowledgeBase:
    def __init__(self):
        self.learned_patterns = self._load_learned_patterns()
    
    def _load_learned_patterns(self):
        """Load learned patterns from Frappe doctype"""
        try:
            patterns = frappe.get_all(
                'Document Pattern',
                fields=['document_type', 'field_patterns', 'confidence', 'sample_count'],
                filters={'is_active': 1}
            )
            return {p['document_type']: json.loads(p['field_patterns']) for p in patterns}
        except:
            # Initialize with basic patterns if no data exists
            return self._get_initial_patterns()
    
    def _get_initial_patterns(self):
        """Initial patterns based on your sample documents"""
        return {
            'saudi_iqama': {
                'name_patterns': [
                    {'pattern': r'([A-Z]{2,} [A-Z]{2,} [A-Z]{2,} [A-Z]{2,})', 'confidence': 0.9},
                    {'pattern': r'([\u0600-\u06FF\s]{3,} [\u0600-\u06FF\s]{3,})', 'confidence': 0.8}
                ],
                'id_patterns': [
                    {'pattern': r'رقم الهوية[\s:]*(\d{4}/\d{2}/\d{2})', 'confidence': 0.7},
                    {'pattern': r'(\d{10})', 'confidence': 0.6}
                ],
                'nationality_patterns': [
                    {'pattern': r'الجنسية[\s:]*([\u0600-\u06FF]+)', 'confidence': 0.8}
                ]
            },
            'pakistani_passport': {
                'name_patterns': [
                    {'pattern': r'([A-Z]+<<[A-Z]+<<<<<<<<<<<<<<<<<<<<<<<<<<<<)', 'confidence': 0.9},
                    {'pattern': r'P<[A-Z]+<([A-Z]+)<<([A-Z]+)', 'confidence': 0.95}
                ],
                'id_patterns': [
                    {'pattern': r'([A-Z]{2}\d{7,})', 'confidence': 0.9},
                    {'pattern': r'CM\d{7,}', 'confidence': 0.8}
                ],
                'nationality_patterns': [
                    {'pattern': r'Islamic Republic of Pakistan', 'confidence': 0.9}
                ]
            },
            'saudi_visa': {
                'name_patterns': [
                    {'pattern': r'Name[\s:]*([A-Z]{2,} [A-Z]{2,})', 'confidence': 0.9},
                    {'pattern': r'الاسم[\s:]*([A-Z]{2,} [A-Z]{2,})', 'confidence': 0.8}
                ],
                'id_patterns': [
                    {'pattern': r'Passport No\.[\s:]*([A-Z0-9]{6,})', 'confidence': 0.9},
                    {'pattern': r'Visa No\.[\s:]*(\d{9,})', 'confidence': 0.8}
                ],
                'nationality_patterns': [
                    {'pattern': r'Nationality[\s:]*([A-Za-z]+)', 'confidence': 0.9},
                    {'pattern': r'الجنسية[\s:]*([\u0600-\u06FF]+)', 'confidence': 0.8}
                ]
            }
        }
    
    def save_learned_pattern(self, doc_type, field_type, pattern, confidence, sample_text):
        """Save new learned pattern to database"""
        try:
            # Create pattern hash for uniqueness
            pattern_hash = hashlib.md5(f"{doc_type}_{field_type}_{pattern}".encode()).hexdigest()
            
            # Check if pattern exists
            existing = frappe.get_all(
                'Document Pattern',
                filters={'pattern_hash': pattern_hash}
            )
            
            if not existing:
                doc = frappe.get_doc({
                    'doctype': 'Document Pattern',
                    'document_type': doc_type,
                    'field_type': field_type,
                    'pattern': pattern,
                    'pattern_hash': pattern_hash,
                    'confidence': confidence,
                    'sample_text': sample_text[:500],  # Store sample for verification
                    'sample_count': 1,
                    'is_active': 1,
                    'last_updated': datetime.now()
                })
                doc.insert(ignore_permissions=True)
            else:
                # Update existing pattern confidence
                frappe.db.set_value('Document Pattern', existing[0].name, {
                    'confidence': confidence,
                    'sample_count': frappe.db.get_value('Document Pattern', existing[0].name, 'sample_count') + 1,
                    'last_updated': datetime.now()
                })
            
            frappe.db.commit()
            self.learned_patterns = self._load_learned_patterns()  # Reload patterns
            
        except Exception as e:
            frappe.log_error(f"Failed to save pattern: {str(e)}")
    
    def get_patterns_for_document(self, doc_type, field_type):
        """Get learned patterns for specific document and field type"""
        if doc_type in self.learned_patterns and field_type in self.learned_patterns[doc_type]:
            return self.learned_patterns[doc_type][field_type]
        return []
    
    def learn_from_successful_extraction(self, doc_type, extracted_data, raw_text):
        """Learn from successful extractions to improve patterns"""
        for field, value in extracted_data.items():
            if value:
                # Create pattern based on context around the extracted value
                pattern = self._generate_pattern_from_context(raw_text, value, field)
                if pattern:
                    # Calculate confidence based on pattern quality
                    confidence = self._calculate_pattern_confidence(pattern, value)
                    self.save_learned_pattern(doc_type, field, pattern, confidence, raw_text)
    
    def _generate_pattern_from_context(self, text, value, field_type):
        """Generate regex pattern from context around extracted value"""
        try:
            # Find the value in text and capture surrounding context
            escaped_value = re.escape(value)
            context_pattern = rf'(.{{0,20}}){escaped_value}(.{{0,20}})'
            match = re.search(context_pattern, text)
            
            if match:
                before_context = match.group(1)
                after_context = match.group(2)
                
                # Create field-specific patterns
                if field_type == 'name':
                    return self._create_name_pattern(before_context, after_context)
                elif field_type == 'id_no':
                    return self._create_id_pattern(before_context, after_context)
                elif field_type == 'nationality':
                    return self._create_nationality_pattern(before_context, after_context)
            
            return None
        except:
            return None
    
    def _create_name_pattern(self, before, after):
        """Create name extraction pattern"""
        # Look for common name indicators
        name_indicators = ['Name', 'اسم', 'الاسم', 'Full Name', 'الاسم الكامل']
        for indicator in name_indicators:
            if indicator in before:
                return rf'{re.escape(indicator)}[\s:]*([A-Za-z\u0600-\u06FF\s]{3,})'
        return rf'([A-Z][a-z]+ [A-Z][a-z]+)'
    
    def _create_id_pattern(self, before, after):
        """Create ID extraction pattern"""
        id_indicators = ['Passport', 'جواز', 'رقم', 'ID', 'هوية', 'Visa']
        for indicator in id_indicators:
            if indicator in before:
                return rf'{re.escape(indicator)}[\s:]*([A-Z0-9]{6,12})'
        return r'([A-Z0-9]{6,12})'
    
    def _create_nationality_pattern(self, before, after):
        """Create nationality extraction pattern"""
        nationality_indicators = ['Nationality', 'جنسية', 'Country', 'بلد']
        for indicator in nationality_indicators:
            if indicator in before:
                return rf'{re.escape(indicator)}[\s:]*([A-Za-z\u0600-\u06FF]{2,})'
        return r'([A-Za-z\u0600-\u06FF]{2,})'
    
    def _calculate_pattern_confidence(self, pattern, value):
        """Calculate confidence score for learned pattern"""
        base_confidence = 0.5
        
        # Higher confidence for specific patterns
        if 'Name' in pattern or 'اسم' in pattern:
            base_confidence += 0.2
        if 'Passport' in pattern or 'هوية' in pattern:
            base_confidence += 0.2
        if 'Nationality' in pattern or 'جنسية' in pattern:
            base_confidence += 0.1
        
        return min(base_confidence, 0.95)  # Cap at 95%