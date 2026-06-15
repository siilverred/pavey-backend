"""
PaddleOCR Service — ekstrak teks dari gambar struk/receipt.

Diinisialisasi secara lazy (hanya saat pertama kali dipakai) agar
startup backend tetap cepat. Model akan di-download otomatis
oleh PaddleOCR ke ~/.paddleocr/ pada first run.
"""

import io
import numpy as np
from PIL import Image
import logging

logger = logging.getLogger(__name__)

_ocr_instance = None


def _get_ocr():
    """Lazy init PaddleOCR — download model hanya sekali."""
    global _ocr_instance
    if _ocr_instance is None:
        try:
            from paddleocr import PaddleOCR
            logger.info("[PaddleOCR] Initializing model (may download on first run)...")
            _ocr_instance = PaddleOCR(
                use_textline_orientation=True,  # deteksi rotasi teks
                lang="en",                      # bahasa English + numerik (cocok untuk struk)
                device="cpu",                   # CPU mode untuk HuggingFace free tier
                enable_mkldnn=False,            # disable MKL-DNN (lebih stabil di Docker)
            )
            logger.info("[PaddleOCR] Model ready.")
        except ImportError:
            raise RuntimeError(
                "PaddleOCR tidak terinstall. Jalankan: pip install paddlepaddle paddleocr"
            )
    return _ocr_instance


def extract_text_from_image(image_bytes: bytes) -> str:
    """
    Ekstrak semua teks dari gambar menggunakan PaddleOCR.

    Args:
        image_bytes: raw bytes dari file gambar (JPEG/PNG/dll)

    Returns:
        String teks yang diekstrak, satu baris per line.

    Raises:
        RuntimeError: jika PaddleOCR gagal memproses gambar.
    """
    try:
        # Convert bytes ke numpy array (format yang diterima PaddleOCR)
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img_array = np.array(img)

        ocr = _get_ocr()
        result = ocr.ocr(img_array, cls=True)

        if not result or result[0] is None:
            return ""

        lines = []
        for line in result[0]:
            # Setiap line: [[box_coords], [text, confidence]]
            if not line or len(line) < 2:
                continue
            text_info = line[1]
            if not text_info or len(text_info) < 2:
                continue
            text = str(text_info[0]).strip()
            confidence = float(text_info[1])
            # Filter teks dengan confidence rendah (<50%)
            if confidence >= 0.5 and text:
                lines.append(text)

        return "\n".join(lines)

    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"PaddleOCR gagal memproses gambar: {str(e)}")
