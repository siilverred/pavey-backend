"""
Receipt OCR Service — ekstrak teks dari gambar struk/receipt menggunakan Gemini Vision.
Menggantikan PaddleOCR untuk menghindari isu dependensi C++ dan oneDNN crash.
"""

import os
import logging
import google.generativeai as genai
from PIL import Image
import io

logger = logging.getLogger(__name__)

# Konfigurasi Gemini API
_gemini_api_key = os.getenv("GEMINI_API_KEY")
if _gemini_api_key:
    genai.configure(api_key=_gemini_api_key)

def extract_text_from_image(image_bytes: bytes) -> str:
    """
    Ekstrak semua teks dari gambar menggunakan Gemini 1.5 Flash Vision.

    Returns:
        String teks yang diekstrak.
    """
    if not _gemini_api_key:
        logger.error("[OCR] GEMINI_API_KEY tidak dikonfigurasi.")
        raise RuntimeError("GEMINI_API_KEY tidak dikonfigurasi. OCR tidak tersedia.")

    try:
        img = Image.open(io.BytesIO(image_bytes))
        
        # Konversi ke RGB jika formatnya RGBA (PNG transparan) dll
        if img.mode != 'RGB':
            img = img.convert('RGB')

        logger.info("[OCR] Mengirim gambar ke Gemini Vision API...")
        
        # Gunakan model gemini-1.5-flash untuk task multimodal ringan
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = (
            "You are an OCR engine. Extract all the text from this receipt image. "
            "Output the text line by line exactly as it appears in the image, "
            "preserving the original layout as much as possible. "
            "Do not add any additional conversational text."
        )
        
        response = model.generate_content([prompt, img])
        
        text = response.text.strip()
        
        if not text:
            logger.warning("[OCR] Gemini tidak mengekstrak teks apa pun.")
            return ""

        logger.info(f"[OCR] Berhasil mengekstrak {len(text.splitlines())} baris teks.")
        return text

    except Exception as e:
        logger.error(f"[OCR] Error Gemini API: {e}")
        raise RuntimeError(f"Gagal memproses gambar untuk OCR: {str(e)}")