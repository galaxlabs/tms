import os
import frappe
from PIL import Image, ImageOps, ImageEnhance
from frappe.utils.file_manager import get_file_path

def preprocess_for_ocr(file_url: str) -> str:
    """
    Returns a NEW file_url of enhanced image for OCR.
    """
    # file_url like "/private/files/abc.jpg"
    abs_path = get_file_path(file_url)
    img = Image.open(abs_path)

    # normalize orientation + grayscale
    img = ImageOps.exif_transpose(img)
    img = img.convert("L")

    # upscale a bit (helps small text)
    w, h = img.size
    img = img.resize((int(w * 1.5), int(h * 1.5)))

    # contrast + sharpness
    img = ImageEnhance.Contrast(img).enhance(1.8)
    img = ImageEnhance.Sharpness(img).enhance(2.0)

    # save
    out_name = os.path.basename(abs_path).rsplit(".", 1)[0] + "_ocr.png"
    out_rel = f"/private/files/{out_name}"
    out_abs = get_file_path(out_rel)
    img.save(out_abs, "PNG", optimize=True)

    return out_rel
