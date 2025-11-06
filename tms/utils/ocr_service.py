# tms/utils/ocr_service.py
import frappe
from pathlib import Path
from typing import Tuple, Optional
import base64
import json

# Import your existing and new OCR utilities
from tms.utils.openai_ocr_utils import extract_text_openai  # Your existing function
from tms.utils.deepseek_ocr_utils import extract_text_deepseek  # To be created
from tms.utils.parser import parse_passenger_details
from google.cloud import vision  # For Google Vision

class OCRService:
    def __init__(self):
        # Define available engines in priority order
        self.engines = [
            ("deepseek", self._deepseek_ocr),
            ("google_vision", self._google_vision_ocr),
        ]
    
    def extract_text(self, file_path: str, preferred_engine: str = None) -> Tuple[str, str]:
        """
        Extract text using multiple OCR engines with fallback.
        Returns: (extracted_text, engine_used)
        """
        file_path = self._resolve_file_path(file_path)
        
        # Try preferred engine first if specified
        if preferred_engine:
            for engine_name, engine_func in self.engines:
                if engine_name == preferred_engine:
                    try:
                        text = engine_func(file_path)
                        if self._is_valid_text(text):
                            return text, engine_name
                    except Exception as e:
                        frappe.logger().warning(f"[OCR] {preferred_engine} failed: {e}")
                        break  # Break and proceed to fallback
        
        # Try all engines in order as fallback
        for engine_name, engine_func in self.engines:
            try:
                frappe.logger().info(f"[OCR] Trying {engine_name}...")
                text = engine_func(file_path)
                if self._is_valid_text(text):
                    frappe.logger().info(f"[OCR] Success with {engine_name}")
                    return text, engine_name
            except Exception as e:
                frappe.logger().warning(f"[OCR] {engine_name} failed: {e}")
                continue
        
        raise Exception("All OCR engines failed")
    
    def _deepseek_ocr(self, file_path: str) -> str:
        """Extract text using DeepSeek-OCR"""
        return extract_text_deepseek(file_path)
    
    def _google_vision_ocr(self, file_path: str) -> str:
        """Extract text using Google Vision API"""
        client = vision.ImageAnnotatorClient()
        with open(file_path, "rb") as image_file:
            content = image_file.read()
        image = vision.Image(content=content)
        response = client.text_detection(image=image)
        
        if response.text_annotations:
            return response.text_annotations[0].description
        return ""
    
    def _resolve_file_path(self, file_url: str) -> str:
        """Convert file URL to absolute path"""
        if file_url.startswith('/private/files/'):
            return frappe.get_site_path('private', 'files', Path(file_url).name)
        elif file_url.startswith('/files/'):
            return frappe.get_site_path('public', 'files', Path(file_url).name)
        else:
            return frappe.get_site_path(file_url.lstrip('/'))
    
    def _is_valid_text(self, text: str) -> bool:
        """Check if extracted text is meaningful for government IDs"""
        if not text or len(text.strip()) < 10:
            return False
        # Check for common ID/passport indicators
        id_indicators = ['name', 'passport', 'id', 'nationality', 'date', 'birth', 'issu', 'expir']
        text_lower = text.lower()
        return any(indicator in text_lower for indicator in id_indicators)