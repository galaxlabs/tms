import pytesseract
from PIL import Image
import frappe, os

def extract_text_from_file(file_url):
    file_path = frappe.get_site_path("private", "files", os.path.basename(file_url))
    image = Image.open(file_path)
    text = pytesseract.image_to_string(image, lang="eng+ara")  # supports Arabic + English
    frappe.logger().info(f"OCR Text Extracted: {text[:150]}")
    return text
