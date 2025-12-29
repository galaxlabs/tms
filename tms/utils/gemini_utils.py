import frappe
import google.generativeai as genai
from PIL import Image
import requests
from io import BytesIO

def get_gemini_ocr(file_url, prompt="Extract all text from this document and format it as JSON."):
    """
    Downloads an image from a URL and processes it using Google Gemini OCR.
    """
    # 1. Get API Key from System Settings or Site Config
    api_key = frappe.conf.get("gemini_api") 
    if not api_key:
        frappe.throw("Gemini API Key not found in site_config.json")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.0-flash')

    try:
        # 2. Download the image (Handle WhatsApp media headers if needed)
        response = requests.get(file_url)
        img = Image.open(BytesIO(response.content))

        # 3. Call Gemini Vision
        # You can pass a specific prompt to get structured TMS data (like 'Extract Plate Number')
        response = model.generate_content([prompt, img])
        
        return response.text
    except Exception as e:
        frappe.log_error(message=str(e), title="Gemini OCR Error")
        return None