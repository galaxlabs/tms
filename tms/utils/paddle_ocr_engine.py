# tms/tms/utils/paddle_ocr_engine.py

from __future__ import annotations
from typing import List, Dict, Any

from paddleocr import PaddleOCR


# You can reuse a single OCR instance (expensive to init)
_paddle_ocr = PaddleOCR(
    use_angle_cls=True,
    lang="en",  # later you can create one more for 'ar'
    show_log=False,
)


def paddle_ocr_boxes(local_path: str) -> List[Dict[str, Any]]:
    """
    Run PaddleOCR on an image and return list of boxes with text + confidence.
    """
    result = _paddle_ocr.ocr(local_path, cls=True)
    boxes = []
    for line in result:
        for box, (text, conf) in line:
            boxes.append({
                "bbox": box,
                "text": text,
                "confidence": float(conf),
            })
    return boxes


def paddle_ocr_text(local_path: str) -> str:
    """Return all detected text joined by newlines."""
    boxes = paddle_ocr_boxes(local_path)
    return "\n".join(b["text"] for b in boxes)
