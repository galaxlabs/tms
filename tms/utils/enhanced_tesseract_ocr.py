# tms/utils/enhanced_tesseract_ocr.py
import frappe
import cv2
import numpy as np
import pytesseract
from PIL import Image
import json
import os
from pathlib import Path
import re

class EnhancedTesseractOCR:
    def __init__(self):
        self.tessdata_dir = self._setup_tessdata()
        self.learning_data_path = frappe.get_site_path("private", "ocr_learning_data.json")
        self.load_learning_data()
    
    def _setup_tessdata(self):
        """Setup Tesseract data directory"""
        tessdata_dir = frappe.get_site_path("private", "tessdata")
        os.makedirs(tessdata_dir, exist_ok=True)
        return tessdata_dir
    
    def load_learning_data(self):
        """Load learned OCR patterns and corrections"""
        try:
            if os.path.exists(self.learning_data_path):
                with open(self.learning_data_path, 'r') as f:
                    self.learning_data = json.load(f)
            else:
                self.learning_data = {
                    "name_patterns": [],
                    "id_patterns": [],
                    "nationality_patterns": [],
                    "corrections": {},
                    "document_templates": {}
                }
        except Exception as e:
            frappe.log_error(f"Loading OCR learning data failed: {e}")
            self.learning_data = {
                "name_patterns": [],
                "id_patterns": [],
                "nationality_patterns": [],
                "corrections": {},
                "document_templates": {}
            }
    
    def detect_language(self, image_path):
        """Detect if text is primarily Arabic or English"""
        try:
            # Try English first
            eng_text = self.extract_text_with_config(image_path, 'eng')
            # Try Arabic
            ara_text = self.extract_text_with_config(image_path, 'ara')
            
            # Count meaningful characters
            eng_chars = len(re.findall(r'[A-Za-z]', eng_text))
            ara_chars = len(re.findall(r'[\u0600-\u06FF]', ara_text))
            
            if ara_chars > eng_chars * 2:  # More Arabic characters
                return 'ara'
            else:
                return 'eng'
        except Exception as e:
            frappe.log_error(f"Language detection failed: {e}")
            return 'eng+ara'  # Fallback to both
    
    def extract_text_with_config(self, image_path, lang_config):
        """Extract text with specific language configuration"""
        try:
            processed_img = self.preprocess_image(image_path)
            if processed_img is None:
                return ""
            
            custom_config = r'--oem 3 --psm 6 -c preserve_interword_spaces=1'
            text = pytesseract.image_to_string(processed_img, lang=lang_config, config=custom_config)
            return text.strip()
        except Exception as e:
            frappe.log_error(f"Tesseract extraction with {lang_config} failed: {e}")
            return ""
    
    def preprocess_image(self, image_path):
        """Enhanced image preprocessing for better OCR accuracy"""
        try:
            # Read image
            img = cv2.imread(image_path)
            if img is None:
                raise ValueError("Could not read image")
            
            # Convert to grayscale
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # Resize image if too small
            height, width = gray.shape
            if height < 300 or width < 300:
                scale = max(600/height, 600/width)
                new_width = int(width * scale)
                new_height = int(height * scale)
                gray = cv2.resize(gray, (new_width, new_height), interpolation=cv2.INTER_CUBIC)
            
            # Noise removal
            denoised = cv2.fastNlMeansDenoising(gray)
            
            # Apply different thresholding for better text extraction
            # Try adaptive threshold
            thresh = cv2.adaptiveThreshold(denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                         cv2.THRESH_BINARY, 11, 2)
            
            # Morphological operations to clean up image
            kernel = np.ones((1, 1), np.uint8)
            processed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
            processed = cv2.morphologyEx(processed, cv2.MORPH_OPEN, kernel)
            
            return processed
        except Exception as e:
            frappe.log_error(f"Image preprocessing failed: {e}")
            return None
    
    def extract_text_with_tesseract(self, image_path):
        """Extract text using smart language detection"""
        try:
            # Detect language first
            detected_lang = self.detect_language(image_path)
            frappe.logger().info(f"Detected language: {detected_lang}")
            
            # Extract with detected language
            if detected_lang == 'ara':
                text = self.extract_text_with_config(image_path, 'ara')
                # Also try with English to catch any mixed content
                eng_text = self.extract_text_with_config(image_path, 'eng')
                if len(eng_text) > len(text) * 0.5:  # If significant English text
                    text = eng_text + " " + text
            elif detected_lang == 'eng':
                text = self.extract_text_with_config(image_path, 'eng')
            else:
                text = self.extract_text_with_config(image_path, 'eng+ara')
            
            # Convert Arabic numerals to English
            text = self.convert_arabic_numerals(text)
            
            # Apply learned corrections
            text = self.apply_corrections(text)
            
            return text.strip()
        except Exception as e:
            frappe.log_error(f"Smart OCR extraction failed: {e}")
            return ""
    
    def convert_arabic_numerals(self, text):
        """Convert Arabic/Indic numerals to English numerals"""
        try:
            # Arabic numerals to English
            arabic_to_english = {
                '٠': '0', '۰': '0', '٠': '0',
                '١': '1', '۱': '1', '١': '1',
                '٢': '2', '۲': '2', '٢': '2', 
                '٣': '3', '۳': '3', '٣': '3',
                '٤': '4', '۴': '4', '٤': '4',
                '٥': '5', '۵': '5', '٥': '5',
                '٦': '6', '۶': '6', '٦': '6',
                '٧': '7', '۷': '7', '٧': '7',
                '٨': '8', '۸': '8', '٨': '8',
                '٩': '9', '۹': '9', '٩': '9'
            }
            
            for arabic_num, english_num in arabic_to_english.items():
                text = text.replace(arabic_num, english_num)
            
            return text
        except Exception as e:
            frappe.log_error(f"Numeral conversion failed: {e}")
            return text
    
    def apply_corrections(self, text):
        """Apply learned text corrections"""
        try:
            for wrong, correct in self.learning_data.get("corrections", {}).items():
                text = text.replace(wrong, correct)
            return text
        except Exception as e:
            frappe.log_error(f"Applying OCR corrections failed: {e}")
            return text
    
    def extract_structured_data(self, text):
        """Extract structured data from OCR text with improved patterns"""
        try:
            # Clean text
            text = self.clean_text(text)
            frappe.logger().info(f"OCR Text for parsing: {text}")
            
            # Initialize result
            result = {
                "name": "",
                "id_no": "",
                "nationality": "",
                "confidence": 0
            }
            
            # Extract using improved patterns
            name = self.extract_name_improved(text)
            id_no = self.extract_id_number_improved(text)
            nationality = self.extract_nationality_improved(text)
            
            result.update({
                "name": name,
                "id_no": id_no,
                "nationality": nationality,
                "confidence": self.calculate_confidence_improved(text, name, id_no, nationality)
            })
            
            frappe.logger().info(f"Parsed data: {result}")
            return result
        except Exception as e:
            frappe.log_error(f"Extracting structured data failed: {e}")
            return {
                "name": "",
                "id_no": "",
                "nationality": "",
                "confidence": 0
            }
    
    def extract_name_improved(self, text):
        """Improved name extraction for both Arabic and English"""
        try:
            # English name patterns
            eng_patterns = [
                r'(?:Name|NAME)[:\s\-]*([A-Z][A-Za-z\s]{2,}(?:\s[A-Z][A-Za-z\s]{1,})*)',
                r'([A-Z][a-z]+\s+[A-Z][a-z]+)',  # First Last format
                r'(?:اسم|الاسم)[:\s\-]*([\u0600-\u06FF\s]{3,})',  # Arabic name
            ]
            
            for pattern in eng_patterns:
                match = re.search(pattern, text, re.IGNORECASE | re.UNICODE)
                if match:
                    name = match.group(1).strip()
                    if len(name) > 2 and not self.is_gibberish(name):
                        return name
            
            # Look for any reasonable name-like pattern
            words = text.split()
            potential_names = []
            for word in words:
                if (len(word) >= 3 and 
                    (re.match(r'^[A-Z][a-z]+$', word) or 
                     re.match(r'^[\u0600-\u06FF]{2,}$', word))):
                    potential_names.append(word)
            
            if len(potential_names) >= 2:
                return ' '.join(potential_names[:2])  # Take first two reasonable words
            
            return ""
        except Exception as e:
            frappe.log_error(f"Improved name extraction failed: {e}")
            return ""
    
    def extract_id_number_improved(self, text):
        """Improved ID/Passport number extraction"""
        try:
            # More comprehensive ID patterns
            id_patterns = [
                r'(?:ID|رقم|Passport|بطاقة|هوية)[\s:\-]*([A-Z0-9]{6,})',
                r'([A-Z]{1,2}[0-9]{6,})',  # Passport format
                r'([0-9]{9,})',  # National ID format
                r'(?:ID\s*No\.?|Passport\s*No\.?)[\s:\-]*([A-Z0-9]{6,})',
            ]
            
            for pattern in id_patterns:
                matches = re.findall(pattern, text, re.IGNORECASE | re.UNICODE)
                for match in matches:
                    if len(match) >= 6 and self.is_valid_id_format(match):
                        return match
            
            return ""
        except Exception as e:
            frappe.log_error(f"Improved ID extraction failed: {e}")
            return ""
    
    def extract_nationality_improved(self, text):
        """Improved nationality extraction"""
        try:
            nationality_patterns = [
                r'(?:Nationality|الجنسية)[\s:\-]*([A-Za-z\u0600-\u06FF\s]{2,})',
                r'(?:Country|الدولة)[\s:\-]*([A-Za-z\u0600-\u06FF\s]{2,})',
                r'(?:مواطن|جنسية)[\s:\-]*([\u0600-\u06FF\s]{2,})',
            ]
            
            for pattern in nationality_patterns:
                match = re.search(pattern, text, re.IGNORECASE | re.UNICODE)
                if match:
                    nationality = match.group(1).strip()
                    if len(nationality) >= 2:
                        return nationality
            
            return ""
        except Exception as e:
            frappe.log_error(f"Improved nationality extraction failed: {e}")
            return ""
    
    def is_gibberish(self, text):
        """Check if text looks like gibberish"""
        if len(text) < 3:
            return True
        
        # Check for repetitive patterns or too many special characters
        if re.search(r'(.)\1{2,}', text):  # Repeated characters
            return True
        
        # Check if it's mostly non-alphanumeric
        alphanumeric_ratio = len(re.findall(r'[A-Za-z0-9\u0600-\u06FF]', text)) / len(text)
        if alphanumeric_ratio < 0.5:
            return True
            
        return False
    
    def is_valid_id_format(self, id_text):
        """Check if extracted ID looks valid"""
        if len(id_text) < 6:
            return False
        
        # Should have mix of letters and numbers, or just numbers
        has_letters = bool(re.search(r'[A-Za-z]', id_text))
        has_numbers = bool(re.search(r'[0-9]', id_text))
        
        if has_letters and has_numbers:
            return True
        elif has_numbers and len(id_text) >= 9:  # All numbers but long enough
            return True
            
        return False
    
    def calculate_confidence_improved(self, text, name, id_no, nationality):
        """Improved confidence calculation"""
        try:
            confidence = 0
            
            if name and not self.is_gibberish(name):
                confidence += 40
                # Bonus for proper name format
                if re.match(r'^[A-Z][a-z]+\s+[A-Z][a-z]+$', name) or re.match(r'^[\u0600-\u06FF\s]{3,}$', name):
                    confidence += 10
            
            if id_no and self.is_valid_id_format(id_no):
                confidence += 40
            
            if nationality and len(nationality) >= 2:
                confidence += 20
            
            # Bonus for longer meaningful text
            if len(text) > 100:
                confidence += 10
            
            return min(confidence, 100)
        except Exception as e:
            frappe.log_error(f"Improved confidence calculation failed: {e}")
            return 0
    
    def clean_text(self, text):
        """Clean and normalize OCR text"""
        try:
            # Remove extra whitespace
            text = re.sub(r'\s+', ' ', text)
            
            # Remove common OCR artifacts but keep Arabic characters
            text = re.sub(r'[^\w\s\u0600-\u06FF\-\.]', '', text)
            
            return text.strip()
        except Exception as e:
            frappe.log_error(f"Cleaning OCR text failed: {e}")
            return text
    
    # Keep existing methods for learning and verification
    def learn_from_correction(self, original_text, corrected_text):
        """Learn from manual corrections"""
        try:
            if original_text != corrected_text:
                self.learning_data["corrections"][original_text] = corrected_text
                self.save_learning_data()
        except Exception as e:
            frappe.log_error(f"Learning from correction failed: {e}")
    
    def learn_from_verified_data(self, ocr_text, verified_data):
        """Learn from verified correct data"""
        try:
            # Learn name patterns
            if verified_data.get("name"):
                name_pattern = self.create_pattern_from_text(verified_data["name"])
                if name_pattern not in self.learning_data["name_patterns"]:
                    self.learning_data["name_patterns"].append(name_pattern)
            
            # Learn ID patterns
            if verified_data.get("id_no"):
                id_pattern = self.create_pattern_from_text(verified_data["id_no"], is_id=True)
                if id_pattern not in self.learning_data["id_patterns"]:
                    self.learning_data["id_patterns"].append(id_pattern)
            
            self.save_learning_data()
        except Exception as e:
            frappe.log_error(f"Learning from verified data failed: {e}")
    
    def create_pattern_from_text(self, text, is_id=False):
        """Create regex pattern from text for learning"""
        try:
            if is_id:
                return r'(?:ID|رقم|Passport)?\s*' + re.escape(text)
            else:
                return r'(?:Name|اسم|Nationality|الجنسية)?\s*' + re.escape(text)
        except Exception as e:
            frappe.log_error(f"Creating pattern from text failed: {e}")
            return ""
    
    def save_learning_data(self):
        """Save learned patterns to file"""
        try:
            with open(self.learning_data_path, 'w') as f:
                json.dump(self.learning_data, f, indent=2)
        except Exception as e:
            frappe.log_error(f"Saving OCR learning data failed: {e}")