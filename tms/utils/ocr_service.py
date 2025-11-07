import frappe
import pytesseract
import requests
from PIL import Image, ImageEnhance, ImageFilter
import os

# Import our intelligent extractor
from .field_extractor import SmartFieldExtractor

def extract_text_unified(image_path, use_openai=False, openai_key=None):
    """
    Unified OCR service with self-learning intelligence
    """
    # Initialize intelligent extractor
    extractor = SmartFieldExtractor()
    
    # First try Tesseract with multiple language support
    try:
        image = Image.open(image_path)
        if image.mode != 'L':
            image = image.convert('L')
        
        # Enhanced preprocessing for better international document OCR
        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(2.0)
        enhancer = ImageEnhance.Sharpness(image)
        image = enhancer.enhance(2.0)
        image = image.filter(ImageFilter.MedianFilter())
        
        # OCR with multiple languages for international documents
        custom_config = r'--oem 3 --psm 6 -c preserve_interword_spaces=1'
        text = pytesseract.image_to_string(image, lang='eng+ara+urd', config=custom_config)
        
        if text and len(text.strip()) > 10:
            # Use intelligent field extraction
            extracted_data = extractor.extract_fields(text)
            
            return {
                'text': text,
                'engine': 'tesseract',
                'structured_data': True,
                'passenger_data': extracted_data
            }
    except Exception as e:
        frappe.log_error(f"Tesseract failed: {str(e)}")
    
    # Fallback to OCR.space for difficult documents
    try:
        api_key = 'helloworld'  # Free key
        url = 'https://api.ocr.space/parse/image'
        
        with open(image_path, 'rb') as f:
            file_data = f.read()
        
        payload = {
            'apikey': api_key, 
            'language': 'eng',
            'OCREngine': 2,
            'isOverlayRequired': False
        }
        files = {'file': ('document.jpg', file_data, 'image/jpeg')}
        
        response = requests.post(url, files=files, data=payload, timeout=30)
        result = response.json()
        
        if result.get('ParsedResults'):
            text = result['ParsedResults'][0].get('ParsedText', '')
            if text:
                # Use intelligent field extraction
                extracted_data = extractor.extract_fields(text)
                
                return {
                    'text': text,
                    'engine': 'ocrspace',
                    'structured_data': True,
                    'passenger_data': extracted_data
                }
    except Exception as e:
        frappe.log_error(f"OCR.space failed: {str(e)}")
    
    return {
        'text': '',
        'engine': 'none',
        'structured_data': False,
        'passenger_data': {}
    }