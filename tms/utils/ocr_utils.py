# apps/tms/tms/utils/ocr_utils.py

from __future__ import annotations

import os
import frappe
import pytesseract
from PIL import Image

# Optional libraries for Arabic shaping (do NOT crash if missing)
try:
    import arabic_reshaper
except Exception:
    arabic_reshaper = None

try:
    from bidi.algorithm import get_display
except Exception:
    get_display = None


def _preprocess_image(image_path: str) -> Image.Image:
    """Light preprocessing using PIL only (stable in production)."""
    img = Image.open(image_path)
    try:
        img = img.convert("L")  # grayscale
    except Exception:
        pass
    return img


def _fix_arabic(text: str) -> str:
    """Reshape/reorder Arabic for display (optional)."""
    if not text:
        return ""
    if arabic_reshaper is None or get_display is None:
        return text
    try:
        reshaped = arabic_reshaper.reshape(text)
        return get_display(reshaped)
    except Exception:
        return text


def _file_url_to_path(file_url: str) -> str:
    """
    Convert Frappe file_url to absolute local filesystem path.
    Supports:
      /private/files/xxx.jpg
      /files/xxx.jpg
    """
    if not file_url:
        return ""

    filename = os.path.basename(file_url)

    if str(file_url).startswith("/private/"):
        return frappe.get_site_path("private", "files", filename)

    # /files/... or public file
    return frappe.get_site_path("public", "files", filename)


def extract_text_from_file(file_url: str):
    """
    OCR for a File URL stored in Frappe.

    Returns:
      (raw_text, fixed_text)

    Notes:
      - Does not raise if file missing or tesseract missing; returns ("","") and logs error.
      - Uses Tesseract via pytesseract; requires system binary `tesseract` installed.
    """
    file_path = _file_url_to_path(file_url)

    if not file_path or not os.path.exists(file_path):
        frappe.log_error(
            f"OCR file not found. file_url={file_url} -> file_path={file_path}",
            "OCR Utils",
        )
        return "", ""

    return extract_text_from_local_path(file_path)


def extract_text_from_local_path(file_path: str):
    """
    OCR for a direct local path on disk.
    Returns:
      (raw_text, fixed_text)
    """
    if not file_path or not os.path.exists(file_path):
        frappe.log_error(f"OCR local file not found: {file_path}", "OCR Utils")
        return "", ""

    config = "--oem 3 --psm 6 -c preserve_interword_spaces=1"

    try:
        pil_img = _preprocess_image(file_path)
        raw_text = pytesseract.image_to_string(pil_img, lang="eng+ara", config=config)

        # fallback: try original if preprocessing produced too little
        if not raw_text or len(raw_text.strip()) < 10:
            raw_text = pytesseract.image_to_string(
                Image.open(file_path),
                lang="eng+ara",
                config=config,
            )

    except Exception as e:
        # This catches missing `tesseract` binary or any OCR failure
        frappe.log_error(f"tesseract_ocr_failed: {e}", "OCR Utils")
        return "", ""

    fixed_text = _fix_arabic(raw_text)

    # Keep logs short (avoid flooding)
    try:
        frappe.logger().info(f"OCR RAW (first 200): {raw_text[:200]}")
        frappe.logger().info(f"OCR FIXED (first 200): {fixed_text[:200]}")
    except Exception:
        pass

    return raw_text, fixed_text

def extract_digits_from_file(file_url: str) -> str:
    """
    Multi-pass OCR tuned for Saudi/Iqama ID digits.

    Improvements:
    - Adds a dynamic ROI crop by locating "الهوية/رقم" via image_to_data()
      and cropping near it (this is the most reliable for Iqama layout).
    - Keeps your existing fixed crops + enhancement/threshold/scaling passes.
    - Arabic+English digits whitelist.

    Returns: best_digits (string) or "".
    """
    import re
    from PIL import ImageEnhance
    from pytesseract import Output

    file_path = _file_url_to_path(file_url)

    if not file_path or not os.path.exists(file_path):
        frappe.log_error(
            f"Digits OCR file not found. file_url={file_url} -> file_path={file_path}",
            "OCR Utils",
        )
        return ""

    try:
        base = _preprocess_image(file_path)  # grayscale PIL image
        w, h = base.size

        def _threshold(img, cutoff: int):
            try:
                return img.point(lambda p: 255 if p > cutoff else 0)
            except Exception:
                return img

        def _scale(img, factor: int):
            try:
                return img.resize((img.size[0] * factor, img.size[1] * factor))
            except Exception:
                return img

        def _enhance(img, c: float, s: float):
            try:
                out = img
                if c != 1.0:
                    out = ImageEnhance.Contrast(out).enhance(c)
                if s != 1.0:
                    out = ImageEnhance.Sharpness(out).enhance(s)
                return out
            except Exception:
                return img

        # -----------------------------
        # Dynamic ROI: find "الهوية/رقم" and crop nearby
        # -----------------------------
        def _find_anchor_roi(img):
            """
            Locate Arabic anchor words using OCR boxes and return a crop around the ID number region.
            We look for: الهوية / ةيوهلا / رقم (OCR variants).
            """
            # Work on a scaled image for better box detection
            scan = _scale(img, 2)

            cfg = "--oem 3 --psm 6"
            try:
                data = pytesseract.image_to_data(scan, lang="ara+eng", config=cfg, output_type=Output.DICT)
            except Exception:
                return None

            n = len(data.get("text", []))
            if n == 0:
                return None

            # common OCR variants
            targets = ("الهوية", "ةيوهلا", "رقم", "هوية", "الهويه", ".ةيوهلا")

            # Pick the best anchor box in the right half of the card
            best = None  # (score, x, y, w, h)
            for i in range(n):
                t = (data["text"][i] or "").strip()
                if not t:
                    continue

                # normalize lightly
                t_norm = t.replace(" ", "").replace("ـ", "")
                if not any(x in t_norm for x in targets):
                    continue

                x = int(data["left"][i])
                y = int(data["top"][i])
                bw = int(data["width"][i])
                bh = int(data["height"][i])

                # Prefer anchors on the right side (Iqama layout)
                # scan image is 2x, so compute center fraction
                cx = x + bw // 2
                frac = cx / max(1, scan.size[0])

                score = 0
                if frac >= 0.55:
                    score += 10
                score += min(10, len(t_norm))  # longer token slightly better
                score += min(10, bh)           # larger box slightly better

                if best is None or score > best[0]:
                    best = (score, x, y, bw, bh)

            if not best:
                return None

            _, ax, ay, aw, ah = best

            # Define ROI near anchor:
            # ID digits appear near the anchor line. We take a rectangle around it.
            # Because Arabic is RTL, digits may appear left of the label.
            pad_y = int(ah * 2.0)
            roi_top = max(0, ay - pad_y)
            roi_bot = min(scan.size[1], ay + int(ah * 3.0))

            # Take a wide band around the anchor line, extending left significantly
            roi_left = max(0, ax - int(scan.size[0] * 0.35))
            roi_right = min(scan.size[0], ax + int(scan.size[0] * 0.10))

            roi = scan.crop((roi_left, roi_top, roi_right, roi_bot))

            # Return ROI scaled back is not needed; we will OCR this ROI directly.
            return roi

        # -----------------------------
        # Crops (fixed + dynamic)
        # -----------------------------
        crops = []

        # Dynamic anchor ROI first (most valuable)
        dyn = _find_anchor_roi(base)
        if dyn is not None:
            crops.append(("dyn_anchor_roi", dyn))

        # Fixed crops
        crops.append(("full", base))
        crops.append(("right_block", base.crop((int(w * 0.55), int(h * 0.15), int(w * 0.98), int(h * 0.55)))))
        crops.append(("id_zone_1", base.crop((int(w * 0.65), int(h * 0.20), int(w * 0.98), int(h * 0.40)))))
        crops.append(("id_zone_2", base.crop((int(w * 0.60), int(h * 0.18), int(w * 0.98), int(h * 0.45)))))
        crops.append(("band", base.crop((0, int(h * 0.18), w, int(h * 0.55)))))

        # Targeted Iqama area guesses
        crops.append(("iqama_id_block_v2", base.crop((int(w * 0.60), int(h * 0.38), int(w * 0.98), int(h * 0.58)))))
        crops.append(("iqama_id_block_v3", base.crop((int(w * 0.58), int(h * 0.34), int(w * 0.99), int(h * 0.60)))))

        # -----------------------------
        # Variants: enhance + threshold + scaling
        # -----------------------------
        thresholds = [120, 145, 165, 185]
        scales = [1, 2, 3]
        contrast_levels = [1.0, 1.7, 2.4]
        sharp_levels = [1.0, 2.0, 3.0]

        variants = []
        for tag, img in crops:
            variants.append((tag, img))

            for c in contrast_levels:
                for s in sharp_levels:
                    if c == 1.0 and s == 1.0:
                        continue
                    variants.append((f"{tag}_c{c}_s{s}", _enhance(img, c, s)))

            for t in thresholds:
                variants.append((f"{tag}_thr{t}", _threshold(img, t)))

        final_imgs = []
        for tag, img in variants:
            for sc in scales:
                if sc == 1:
                    final_imgs.append((tag, img))
                else:
                    final_imgs.append((f"{tag}_x{sc}", _scale(img, sc)))

        # -----------------------------
        # OCR pass
        # -----------------------------
        # Add psm 8 (single word) sometimes helps digits-only blocks
        psm_modes = [6, 7, 8, 11, 13]
        whitelist = "0123456789٠١٢٣٤٥٦٧٨٩"

        results = []
        for tag, img in final_imgs:
            for psm in psm_modes:
                config = (
                    f"--oem 3 --psm {psm} "
                    f"-c tessedit_char_whitelist={whitelist} "
                    "-c preserve_interword_spaces=1"
                )
                try:
                    txt = pytesseract.image_to_string(img, lang="ara+eng", config=config) or ""
                    txt = txt.strip()
                    if txt:
                        results.append((tag, psm, txt))
                except Exception as e:
                    frappe.log_error(f"digits_ocr_failed [{tag} psm={psm}]: {e}", "OCR Utils")

        if not results:
            return ""

        def _score(s: str):
            only_digits = re.sub(r"[^\d٠-٩]", "", s)
            digit_count = len(only_digits)
            runs = re.findall(r"[0-9٠-٩]{8,}", only_digits)  # emphasize long runs
            longest_run = max((len(r) for r in runs), default=0)
            return (longest_run, digit_count, len(s))

        best_tag, best_psm, best_text = max(results, key=lambda r: _score(r[2]))

        try:
            frappe.logger().info(f"DIGITS OCR BEST: tag={best_tag} psm={best_psm} text={best_text[:140]}")
        except Exception:
            pass

        best_digits = re.sub(r"[^\d٠-٩\s]", " ", best_text)
        best_digits = re.sub(r"\s+", " ", best_digits).strip()
        return best_digits

    except Exception as e:
        frappe.log_error(f"digits_ocr_failed: {e}", "OCR Utils")
        return ""
