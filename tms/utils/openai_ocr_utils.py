import frappe
from openai import OpenAI
from pathlib import Path
import base64

def extract_text_openai(image_path: str) -> str:
    """Extracts bilingual text (Arabic + English) using GPT-4o Vision."""
    api_key = frappe.conf.openai_api_key or frappe.get_conf().get("OPENAI_API_KEY")
    client = OpenAI(api_key=api_key)

    # Convert to data URI (works for local files)
    image_file = Path(image_path)
    img_b64 = base64.b64encode(image_file.read_bytes()).decode("utf-8")
    image_url = f"data:image/jpeg;base64,{img_b64}"

    completion = client.chat.completions.create(
        model="gpt-4o-mini",  # or "gpt-4o" for highest accuracy
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Extract all Arabic and English text from this image exactly as shown."},
                    {"type": "image_url", "image_url": image_url},
                ],
            }
        ],
    )

    return completion.choices[0].message.content.strip()
