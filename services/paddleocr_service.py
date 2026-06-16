"""
Receipt OCR Service — ekstrak teks dari gambar struk/receipt menggunakan PaddleOCR.
"""

import os
# Disable oneDNN/MKLDNN to avoid "ConvertPirAttribute2RuntimeAttribute" crash on CPU (e.g., Windows/Linux)
os.environ["FLAGS_use_mkldnn"] = "0"
os.environ["FLAGS_onednn_cpu"] = "0"
os.environ["PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"] = "0"

import logging
import io
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

_ocr_instance = None
_ocr_init_error = None


def _get_ocr():
    global _ocr_instance, _ocr_init_error
    if _ocr_instance is not None:
        return _ocr_instance
    if _ocr_init_error is not None:
        raise RuntimeError(f"PaddleOCR init sebelumnya gagal: {_ocr_init_error}")

    try:
        from paddleocr import PaddleOCR
        logger.info("[OCR] Initializing PaddleOCR model...")
        
        # Inspect PaddleOCR signature to safely choose parameters and avoid double instantiation error
        import inspect
        sig = inspect.signature(PaddleOCR.__init__)
        if 'use_textline_orientation' in sig.parameters:
            _ocr_instance = PaddleOCR(
                use_textline_orientation=False,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                lang='en'
            )
        else:
            _ocr_instance = PaddleOCR(use_angle_cls=True, lang='en')

        logger.info("[OCR] PaddleOCR model ready.")
        return _ocr_instance
    except ImportError as e:
        _ocr_init_error = f"ImportError: {str(e)}"
        raise RuntimeError(
            "PaddleOCR tidak terinstall. Jalankan: pip install paddleocr paddlepaddle"
        )
    except Exception as e:
        import traceback
        _ocr_init_error = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
        raise RuntimeError(f"PaddleOCR init gagal: {_ocr_init_error}")


def extract_text_from_image(image_bytes: bytes) -> str:
    """
    Ekstrak semua teks dari gambar menggunakan PaddleOCR.

    Returns:
        String teks yang diekstrak, satu baris per deteksi.
    """
    try:
        # Konversi bytes ke PIL Image
        img = Image.open(io.BytesIO(image_bytes))

        # Pastikan format RGB (PNG transparan / RGBA tidak didukung langsung)
        if img.mode != 'RGB':
            img = img.convert('RGB')

        img_array = np.array(img)

        logger.info("[OCR] Membaca gambar menggunakan PaddleOCR...")
        ocr = _get_ocr()

        # Run prediction with multi-method fallback compatibility
        if hasattr(ocr, 'predict'):
            try:
                result = ocr.predict(img_array)
            except Exception as e:
                logger.warning(f"[OCR] predict() failed, falling back to ocr(): {e}")
                result = ocr.ocr(img_array)
        else:
            result = ocr.ocr(img_array)

        lines = []
        if result and len(result) > 0:
            first_res = result[0]
            if isinstance(first_res, dict):
                # PaddleOCR v3/v4 (PaddleX dict format)
                rec_texts = first_res.get('rec_texts', [])
                rec_scores = first_res.get('rec_scores', [])
                for text, confidence in zip(rec_texts, rec_scores):
                    if confidence >= 0.2 and str(text).strip():
                        lines.append(str(text).strip())
            elif isinstance(first_res, list):
                # Traditional PaddleOCR list format
                for line in first_res:
                    if isinstance(line, list) and len(line) >= 2:
                        text_info = line[1]
                        if isinstance(text_info, (list, tuple)) and len(text_info) >= 2:
                            text, confidence = text_info[0], text_info[1]
                            if confidence >= 0.2 and str(text).strip():
                                lines.append(str(text).strip())

        if not lines:
            logger.warning("[OCR] PaddleOCR tidak mengekstrak teks apa pun.")
            return ""

        extracted_text = "\n".join(lines)
        logger.info(f"[OCR] Berhasil mengekstrak {len(lines)} baris teks.")
        return extracted_text

    except RuntimeError:
        raise
    except Exception as e:
        logger.error(f"[OCR] Error PaddleOCR: {e}")
        raise RuntimeError(f"Gagal memproses gambar untuk OCR: {str(e)}")