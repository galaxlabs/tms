# tms/utils/deepseek_ocr_utils.py
import frappe
import requests
import base64
from transformers import AutoModel, AutoTokenizer
import torch

def extract_text_deepseek(image_path: str) -> str:
    """
    Extract text from image using DeepSeek-OCR.
    Requires the model to be set up in the environment[citation:2][citation:7].
    """
    try:
        # Load model and tokenizer (should be cached after first load)
        model_name = "deepseek-ai/DeepSeek-OCR"
        
        tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
        model = AutoModel.from_pretrained(
            model_name,
            trust_remote_code=True,
            use_safetensors=True,
        )
        
        # Move to GPU if available
        if torch.cuda.is_available():
            model = model.eval().cuda().to(torch.bfloat16)
        else:
            model = model.eval()
        
        # Use a prompt tailored for government documents[citation:3]
        prompt = "<image>\n<|grounding|>Extract all text from this government ID or passport accurately."
        
        # Run inference[citation:2]
        result = model.infer(
            tokenizer,
            prompt=prompt,
            image_file=image_path,
            output_path="/tmp",
            base_size=1024,
            image_size=640,
            crop_mode=True,
            save_results=False,  # Set to True if you want output files
            test_compress=False,
        )
        
        return result.get("text", "")
        
    except Exception as e:
        frappe.log_error(f"DeepSeek OCR failed: {str(e)}", "DeepSeek OCR")
        raise