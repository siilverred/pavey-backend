import os
import sys
from dotenv import load_dotenv

# Load env for GEMINI_API_KEY
load_dotenv('d:/PaveyApp/backend/.env')

from services.paddleocr_service import extract_text_from_image
from routers.receipt import parse_receipt_with_llm

image_path = 'C:/Users/Imagination/.gemini/antigravity-ide/brain/49a89f78-501d-4072-b308-fd5d5aab548c/media__1781602874815.jpg'

with open(image_path, 'rb') as f:
    img_bytes = f.read()

print('Calling OCR...')
try:
    text = extract_text_from_image(img_bytes)
    print('OCR RESULT:')
    print(text)
    print('\nCalling LLM parser...')
    parsed = parse_receipt_with_llm(text)
    import json
    print('PARSED RESULT:')
    print(json.dumps(parsed, indent=2))
except Exception as e:
    print('ERROR:', str(e))
