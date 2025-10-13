import torch
from transformers import AutoProcessor, AutoModelForImageTextToText  # ← new class name
from PIL import Image

MODEL_ID = "allenai/olmOCR-7B-0825"

processor = AutoProcessor.from_pretrained(MODEL_ID)

# ✅ Safer universal load (no accelerate required)
model = AutoModelForImageTextToText.from_pretrained(
    MODEL_ID,
    torch_dtype=torch.float32,
    low_cpu_mem_usage=True
).to("cpu")
model.eval()

def extract_text_olmocr(image_path: str) -> str:
    image = Image.open(image_path).convert("RGB")

    prompt = (
        "Extract all visible text from this image accurately. "
        "Preserve both Arabic and English text exactly as seen."
    )

    inputs = processor(text=prompt, images=image, return_tensors="pt").to(model.device)

    with torch.no_grad():
        generated_ids = model.generate(**inputs, max_new_tokens=2048)
        text = processor.batch_decode(generated_ids, skip_special_tokens=True)[0]

    return text.strip()

# from PIL import Image
# import torch
# from transformers import AutoProcessor, AutoModelForSeq2SeqLM
# # or the specific class used by olmOCR, depending on toolkit

# # Load model & processor once (global)
# MODEL_ID = "allenai/olmOCR-7B-0825"
# processor = AutoProcessor.from_pretrained(MODEL_ID)
# model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_ID, torch_dtype=torch.float16)
# device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
# model = model.to(device)
# model.eval()

# def extract_text_olmocr(image_path: str) -> str:
#     """
#     Uses olmOCR model to extract text from image.
#     """
#     image = Image.open(image_path).convert("RGB")
#     # Preprocess image + create inputs for model
#     inputs = processor(images=image, return_tensors="pt").to(device)
#     outputs = model.generate(**inputs, max_new_tokens=1024)
#     texts = processor.batch_decode(outputs, skip_special_tokens=True)
#     return texts[0].strip()
