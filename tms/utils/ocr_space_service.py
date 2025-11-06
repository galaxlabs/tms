import frappe
import requests
import json
import os
from PIL import Image
import io

def extract_text_via_ocrspace(file_path, api_key, overlay=False, language='eng'):
    """
    Fixed version: Handles file type detection and proper file upload
    """
    try:
        # OCR.space API endpoint
        url = 'https://api.ocr.space/parse/image'
        
        # Get file extension and validate
        file_extension = os.path.splitext(file_path)[1].lower()
        valid_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.pdf', '.tif', '.tiff']
        
        if file_extension not in valid_extensions:
            frappe.log_error(f"Invalid file extension: {file_extension}", "OCR Space API")
            return None
        
        # Read file in binary mode
        with open(file_path, 'rb') as f:
            file_data = f.read()
        
        # Determine content type based on extension
        content_type = 'image/jpeg'  # default
        if file_extension == '.png':
            content_type = 'image/png'
        elif file_extension == '.gif':
            content_type = 'image/gif'
        elif file_extension == '.bmp':
            content_type = 'image/bmp'
        elif file_extension == '.pdf':
            content_type = 'application/pdf'
        
        # Prepare the payload with explicit file type
        payload = {
            'isOverlayRequired': overlay,
            'apikey': api_key,
            'language': language,
            'OCREngine': 2,  # Use Engine 2 for better accuracy
            'scale': True,
            'isTable': False,
        }
        
        # Create a clean filename without spaces or special chars
        clean_filename = f"document{file_extension}"
        
        # Send the request with proper file handling
        files = {'file': (clean_filename, file_data, content_type)}
        
        response = requests.post(
            url,
            files=files,
            data=payload,
            timeout=30
        )
        
        # Parse the JSON response
        result = response.json()
        
        # Check if the request was successful
        if result.get('IsErroredOnProcessing'):
            error_message = result.get('ErrorMessage', ['Unknown API error'])
            if isinstance(error_message, list):
                error_message = ', '.join(error_message)
            frappe.log_error(f"OCR.space Error: {error_message}", "OCR Space API")
            return None
        
        # Extract and return the parsed text
        parsed_results = result.get('ParsedResults', [])
        if parsed_results:
            parsed_text = parsed_results[0].get('ParsedText', '')
            return parsed_text
        else:
            frappe.log_error("No parsed results in OCR.space response", "OCR Space API")
            return None

    except Exception as e:
        frappe.log_error(f"Failed to call OCR.space API: {str(e)}", "OCR Space API")
        return None

def extract_text_via_ocrspace_with_fallback(file_path, api_key):
    """
    Try OCR.space first, if it fails, fallback to Tesseract
    """
    # First try OCR.space
    result = extract_text_via_ocrspace(file_path, api_key)
    
    if result:
        return result, "ocr.space"
    else:
        # Fallback to Tesseract
        frappe.logger().info("OCR.space failed, falling back to Tesseract")
        try:
            import pytesseract
            from PIL import Image, ImageEnhance, ImageFilter
            
            # Preprocess image for better Tesseract results
            image = Image.open(file_path)
            if image.mode != 'L':
                image = image.convert('L')
            
            # Enhance image
            enhancer = ImageEnhance.Contrast(image)
            image = enhancer.enhance(2.0)
            enhancer = ImageEnhance.Sharpness(image)
            image = enhancer.enhance(2.0)
            
            # OCR with Tesseract
            custom_config = r'--oem 3 --psm 6'
            text = pytesseract.image_to_string(image, lang='eng+ara', config=custom_config)
            
            return text, "tesseract"
            
        except Exception as e:
            frappe.log_error(f"Tesseract fallback also failed: {str(e)}", "OCR Fallback")
            return None, "none"