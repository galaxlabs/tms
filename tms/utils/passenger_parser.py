import re
import json
import frappe

def parse_passenger_details(ocr_result):
    """
    Parse OCR text into structured passenger data.
    Handles both raw text and pre-structured JSON from GPT-4.
    """
    if ocr_result.get('structured_data'):
        try:
            # GPT-4 already returned JSON
            data = json.loads(ocr_result['text'])
            return validate_passenger_data(data)
        except:
            pass
    
    # Parse raw text with enhanced patterns
    text = ocr_result['text']
    return parse_raw_ocr_text(text)

def parse_raw_ocr_text(text):
    """Advanced parser for raw OCR text from Tesseract/OCR.space"""
    # Clean text
    text = ' '.join(text.split())
    
    result = {}
    
    # Enhanced name patterns (avoid document text)
    name_patterns = [
        r'(?:Name|اسم|الاسم)[\s:]*([A-Za-z\u0600-\u06FF\s]{2,}(?:\s+[A-Za-z\u0600-\u06FF\s]{1,3}){1,2})(?=\s|$|ID|Passport)',
        r'(?:Full Name|الاسم الكامل)[\s:]*([A-Za-z\u0600-\u06FF\s]{2,}(?:\s+[A-Za-z\u0600-\u06FF\s]{1,3}){1,2})',
        r'(?:Passenger|مسافر)[\s:]*([A-Za-z\u0600-\u06FF\s]{2,}(?:\s+[A-Za-z\u0600-\u06FF\s]{1,3}){1,2})'
    ]
    
    # ID patterns
    id_patterns = [
        r'(?:ID|رقم|Passport|جواز)[\s:]*([A-Z0-9]{6,12})',
        r'(?:Identity|هوية)[\s:]*([A-Z0-9]{6,12})',
        r'([A-Z][0-9]{7,10})',  # Common passport format
        r'(\d{9,12})'  # Numeric IDs
    ]
    
    # Nationality patterns  
    nationality_patterns = [
        r'(?:Nationality|جنسية)[\s:]*([A-Za-z\u0600-\u06FF]{2,20})',
        r'(?:Country|بلد)[\s:]*([A-Za-z\u0600-\u06FF]{2,20})'
    ]
    
    # Extract fields
    for pattern in name_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match and is_valid_name(match.group(1)):
            result['name'] = match.group(1).strip()[:140]  # Respect field limits
            break
    
    for pattern in id_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result['id_no'] = match.group(1).strip()
            break
    
    for pattern in nationality_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result['nationality'] = match.group(1).strip()
            break
    
    return result

def is_valid_name(name):
    """Validate extracted text is actually a name"""
    if not name or len(name) < 2 or len(name) > 50:
        return False
        
    invalid_phrases = ['republic', 'president', 'director', 'bearer', 'concern']
    name_lower = name.lower()
    
    return not any(phrase in name_lower for phrase in invalid_phrases)

def validate_passenger_data(data):
    """Ensure data meets Frappe field requirements"""
    if 'name' in data and len(data['name']) > 140:
        data['name'] = data['name'][:140]
    return data