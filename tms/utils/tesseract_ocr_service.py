import frappe
import pytesseract
from PIL import Image, ImageEnhance, ImageFilter
import os
import re

class TesseractOCRService:
    def __init__(self):
        self.supported_languages = ['eng', 'ara']
    
    def preprocess_image(self, image_path):
        """Enhance image for better OCR accuracy"""
        try:
            image = Image.open(image_path)
            
            # Convert to grayscale
            if image.mode != 'L':
                image = image.convert('L')
            
            # Enhance contrast
            enhancer = ImageEnhance.Contrast(image)
            image = enhancer.enhance(2.0)
            
            # Enhance sharpness
            enhancer = ImageEnhance.Sharpness(image)
            image = enhancer.enhance(2.0)
            
            # Apply slight blur to reduce noise
            image = image.filter(ImageFilter.MedianFilter())
            
            return image
            
        except Exception as e:
            frappe.log_error(f"Image preprocessing failed: {str(e)}", "Tesseract OCR")
            return Image.open(image_path)  # Return original if preprocessing fails
    
    def extract_passenger_data(self, file_path):
        """Extract passenger data from ID image using Tesseract"""
        try:
            # Preprocess image
            processed_image = self.preprocess_image(file_path)
            
            # OCR configuration for IDs/passports
            custom_config = r'--oem 3 --psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789/- \u0600-\u06FF'
            
            # Extract text with multiple language support
            extracted_text = pytesseract.image_to_string(
                processed_image, 
                lang='eng+ara',
                config=custom_config
            )
            
            return self._parse_passenger_info(extracted_text)
            
        except Exception as e:
            frappe.log_error(f"Tesseract OCR failed: {str(e)}", "Tesseract OCR")
            return {"name": None, "id_no": None, "nationality": None}
    
    def _parse_passenger_info(self, text):
        """Parse extracted text into structured passenger data"""
        # Clean the text
        text = ' '.join(text.split())  # Normalize whitespace
        
        # Enhanced patterns for government IDs
        patterns = {
            'name': [
                r'(?:Name|اسم|الاسم)[\s:]*([A-Za-z\u0600-\u06FF\s]{3,})(?=\n|ID|Passport|رقم)',
                r'(?:Full Name|الاسم الكامل)[\s:]*([A-Za-z\u0600-\u06FF\s]{3,})',
                r'^([A-Z][a-z]+ [A-Z][a-z]+)$',
                r'([A-Za-z\u0600-\u06FF]{2,} [A-Za-z\u0600-\u06FF]{2,})'
            ],
            'id_no': [
                r'(?:ID|رقم|Passport|جواز)[\s:]*([A-Z0-9]{6,12})',
                r'(?:National ID|هوية)[\s:]*([A-Z0-9]{6,12})',
                r'([A-Z][0-9]{6,10})',
                r'(\b[0-9]{9,12}\b)'
            ],
            'nationality': [
                r'(?:Nationality|جنسية)[\s:]*([A-Za-z\u0600-\u06FF]{2,})',
                r'(?:Country|بلد)[\s:]*([A-Za-z\u0600-\u06FF]{2,})',
                r'(\b(Saudi|Egyptian|Jordanian|Pakistani|Indian|Bangladeshi)\b)'
            ]
        }
        
        result = {}
        
        # Extract each field
        for field, field_patterns in patterns.items():
            for pattern in field_patterns:
                match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
                if match:
                    result[field] = match.group(1).strip()
                    break  # Take first match
        
        return result

# Global instance
tesseract_service = TesseractOCRService()