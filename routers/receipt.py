from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from services.supabase_client import supabase
from services.paddleocr_service import extract_text_from_image
from services.exchange_service import get_rate_from_idr
from middleware.auth_middleware import get_current_user
from typing import Optional, List
from enum import Enum
import re
import json
import datetime

router = APIRouter()

# ── Auth opsional ────────────────────────────────────────────────────────────
_receipt_security = HTTPBearer(auto_error=False)

def _get_optional_receipt_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(_receipt_security)):
    if not credentials:
        return None
    try:
        user = supabase.auth.get_user(credentials.credentials)
        if user and user.user:
            return user.user
    except Exception:
        pass
    return None


# ── Enums ────────────────────────────────────────────────────────────────────
class ReceiptFunction(str, Enum):
    extract   = "extract"
    split_bill = "split_bill"
    currency  = "currency"
    translate = "translate"

class TargetCurrency(str, Enum):
    USD = "USD"; EUR = "EUR"; SGD = "SGD"; MYR = "MYR"
    JPY = "JPY"; KRW = "KRW"; AUD = "AUD"; GBP = "GBP"
    THB = "THB"; CNY = "CNY"

class TargetLanguage(str, Enum):
    english  = "English"
    japanese = "Japanese"
    korean   = "Korean"
    mandarin = "Mandarin Chinese"
    malay    = "Malay"
    thai     = "Thai"
    arabic   = "Arabic"
    french   = "French"


# ── Helpers ──────────────────────────────────────────────────────────────────
def safe_int(value) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        cleaned = re.sub(r"[^\d]", "", value)
        return int(cleaned) if cleaned else 0
    return 0


def parse_price(text: str) -> int:
    """
    Ubah string harga berbagai format ke integer.
    Contoh: '45.000' → 45000, '177,500' → 177500, '50000' → 50000
    """
    text = text.strip()
    # Hapus simbol mata uang
    text = re.sub(r"[Rp\$€¥₩฿£]", "", text, flags=re.IGNORECASE).strip()
    # Format Indonesia: 45.000 (dot sebagai ribuan) → 45000
    if re.match(r"^\d{1,3}(\.\d{3})+$", text):
        return int(text.replace(".", ""))
    # Format barat: 45,000 → 45000
    if re.match(r"^\d{1,3}(,\d{3})+$", text):
        return int(text.replace(",", ""))
    # Format desimal: 45.50 → ambil bagian integer saja (anggap sen)
    if re.match(r"^\d+\.\d{1,2}$", text):
        # Bisa jadi harga kecil (USD) atau format Indonesia
        parts = text.split(".")
        if len(parts[1]) == 2:
            # Kemungkinan desimal barat (cents)
            return int(float(text))
        else:
            return int(text.replace(".", ""))
    # Hapus semua non-digit
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else 0


# ── Regex patterns untuk parsing struk ───────────────────────────────────────
_PRICE_INLINE = re.compile(
    r"^(.+?)\s+"                             # nama item
    r"(?:(?:x|X|\*)\s*(\d+)\s+)?"           # opsional: qty (x2, *3)
    r"((?:Rp\.?\s*)?[\d.,]+)\s*$"           # harga
)
_PRICE_ONLY   = re.compile(r"^((?:Rp\.?\s*)?[\d.,]{3,})\s*$")
_QTY_PRICE    = re.compile(r"^\s*(\d+)\s*[xX\*]\s*([\d.,]+)\s*$")   # "2 x 15000"
_DATE_PAT     = re.compile(
    r"(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{2,4})"
    r"|(\d{4})[/\-\.](\d{1,2})[/\-\.](\d{1,2})"
)
_TOTAL_KEYS   = {
    "subtotal"       : r"sub\s*total|sub-total|subtotal",
    "tax"            : r"tax|vat|ppn|pajak",
    "service_charge" : r"service\s*charge|service|servis",
    "discount"       : r"disc|diskon|discount|promo",
    "grand_total"    : r"grand\s*total|total\s*bayar|total\s*bill|amount\s*due|total",
}
_SKIP_LINES   = re.compile(
    r"receipt|struk|invoice|faktur|kasir|cashier|thank|terima\s*kasih"
    r"|wifi|password|phone|telp|address|alamat|website|www\.|http"
    r"|no\.\s*meja|table\s*no|order\s*#|order\s*id",
    re.IGNORECASE
)


def _detect_currency(lines: List[str]) -> str:
    text = " ".join(lines).upper()
    if "YEN" in text or "¥" in text or "JPY" in text:
        return "JPY"
    if "KRW" in text or "₩" in text or "WON" in text:
        return "KRW"
    if "USD" in text or "$" in text:
        return "USD"
    if "EUR" in text or "€" in text:
        return "EUR"
    if "SGD" in text:
        return "SGD"
    if "MYR" in text or "RM" in text:
        return "MYR"
    if "THB" in text or "฿" in text or "BAHT" in text:
        return "THB"
    if "AUD" in text:
        return "AUD"
    if "GBP" in text or "£" in text:
        return "GBP"
    # Default: IDR
    return "IDR"


def _extract_date(lines: List[str]) -> Optional[str]:
    for line in lines:
        m = _DATE_PAT.search(line)
        if m:
            try:
                if m.group(4):  # YYYY-MM-DD
                    y, mo, d = int(m.group(4)), int(m.group(5)), int(m.group(6))
                else:           # DD/MM/YYYY atau MM/DD/YYYY
                    a, b, c = int(m.group(1)), int(m.group(2)), int(m.group(3))
                    if c < 100:
                        c += 2000
                    # Heuristik: kalau a > 12 pasti DD, kalau b > 12 pasti DD di posisi b
                    if a > 12:
                        d, mo, y = a, b, c
                    else:
                        mo, d, y = a, b, c
                return f"{y:04d}-{mo:02d}-{d:02d}"
            except Exception:
                pass
    return None


def _extract_merchant(lines: List[str]) -> str:
    """Ambil baris pertama yang bukan harga, tanggal, atau skip line."""
    for line in lines[:6]:
        line = line.strip()
        if not line:
            continue
        if _SKIP_LINES.search(line):
            continue
        if _PRICE_ONLY.match(line):
            continue
        if _DATE_PAT.search(line):
            continue
        if len(line) > 1:
            return line
    return "Unknown"


def parse_receipt_from_ocr(raw_text: str) -> dict:
    """
    Parse teks OCR struk menjadi struktur JSON terstandarisasi.
    Tidak membutuhkan LLM sama sekali — pure regex + heuristic.
    """
    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]

    if not lines:
        return {"error": "Struk tidak terbaca"}

    currency = _detect_currency(lines)
    date     = _extract_date(lines)
    merchant = _extract_merchant(lines)

    # ── Kumpulkan nilai total dulu (scan dari bawah) ──────────────────────
    totals = {k: 0 for k in _TOTAL_KEYS}
    total_line_indices = set()

    for i, line in enumerate(lines):
        lower = line.lower()
        for key, pattern in _TOTAL_KEYS.items():
            if re.search(pattern, lower, re.IGNORECASE):
                # Cari angka di baris yang sama
                nums = re.findall(r"[\d.,]{3,}", line)
                if nums:
                    totals[key] = parse_price(nums[-1])
                    total_line_indices.add(i)
                break

    # ── Parse item ────────────────────────────────────────────────────────
    items = []
    item_id = 1
    pending_name = None   # nama item yang belum punya harga (harga di baris berikutnya)
    pending_qty  = 1

    for i, line in enumerate(lines):
        if i in total_line_indices:
            continue
        if _SKIP_LINES.search(line):
            continue
        if _DATE_PAT.match(line):
            continue
        if line == merchant:
            continue

        # Pattern: "Nama Item    15000"
        m_inline = _PRICE_INLINE.match(line)
        if m_inline:
            name  = m_inline.group(1).strip()
            qty_s = m_inline.group(2)
            price_s = m_inline.group(3)

            qty   = int(qty_s) if qty_s else 1
            price = parse_price(price_s)

            if price == 0:
                pending_name = name
                pending_qty  = qty
                continue

            # Filter nama yang terlalu pendek atau hanya angka
            if len(name) < 2 or re.match(r"^\d+$", name):
                continue

            total_price = price * qty
            items.append({
                "item_id": item_id,
                "item_name": name,
                "quantity": qty,
                "price_per_item": price,
                "total_item_price": total_price
            })
            item_id += 1
            pending_name = None
            continue

        # Pattern: harga saja di baris terpisah (nama ada di baris sebelumnya)
        m_price_only = _PRICE_ONLY.match(line)
        if m_price_only and pending_name:
            price = parse_price(m_price_only.group(1))
            if price > 0:
                items.append({
                    "item_id": item_id,
                    "item_name": pending_name,
                    "quantity": pending_qty,
                    "price_per_item": price,
                    "total_item_price": price * pending_qty
                })
                item_id += 1
            pending_name = None
            pending_qty  = 1
            continue

        # Pattern: "2 x 15000" tanpa nama → tambah qty ke item terakhir
        m_qty = _QTY_PRICE.match(line)
        if m_qty:
            qty   = int(m_qty.group(1))
            price = parse_price(m_qty.group(2))
            if price > 0 and pending_name:
                items.append({
                    "item_id": item_id,
                    "item_name": pending_name,
                    "quantity": qty,
                    "price_per_item": price,
                    "total_item_price": price * qty
                })
                item_id += 1
                pending_name = None
                pending_qty  = 1
            continue

        # Baris nama saja (tidak ada harga) → simpan sebagai pending
        if not _PRICE_ONLY.match(line) and len(line) > 2 and not re.match(r"^\d+$", line):
            pending_name = line
            pending_qty  = 1

    # ── Hitung / validasi totals ──────────────────────────────────────────
    computed_subtotal = sum(it["total_item_price"] for it in items)

    # Kalau subtotal tidak terdeteksi dari teks, hitung dari items
    if totals["subtotal"] == 0 and computed_subtotal > 0:
        totals["subtotal"] = computed_subtotal

    # Kalau grand_total tidak terdeteksi, estimasi dari subtotal + tax + service - discount
    if totals["grand_total"] == 0 and totals["subtotal"] > 0:
        totals["grand_total"] = (
            totals["subtotal"]
            + totals["tax"]
            + totals["service_charge"]
            - totals["discount"]
        )

    if not items and totals["grand_total"] == 0:
        return {"error": "Struk tidak terbaca — coba foto lebih jelas atau pencahayaan lebih baik"}

    return {
        "merchant_name"   : merchant,
        "date"            : date,
        "currency_detected": currency,
        "items"           : items,
        "totals"          : {
            "subtotal"       : totals["subtotal"],
            "tax"            : totals["tax"],
            "service_charge" : totals["service_charge"],
            "discount"       : totals["discount"],
            "grand_total"    : totals["grand_total"],
        }
    }


def translate_items_local(items: list, target_lang: str) -> list:
    """
    Terjemahan sederhana untuk nama item struk menggunakan Groq,
    tapi dengan payload seminimal mungkin (hanya nama item saja).
    Fallback: kembalikan nama asli jika LLM gagal.
    """
    try:
        from services.llama_service import chat_with_llama
        # Hanya kirim nama item, bukan seluruh struktur
        names_only = [{"id": it["item_id"], "n": it["item_name"]} for it in items]
        mini_prompt = json.dumps(names_only, ensure_ascii=False)
        system = (
            f"Translate each item name to {target_lang}. "
            "Return ONLY valid JSON array: [{\"id\":1,\"t\":\"translated\"},...]. No explanation."
        )
        result = chat_with_llama(mini_prompt, system)
        parsed = json.loads(result) if isinstance(result, str) else result
        # Bisa jadi list langsung atau dict dengan key array
        if isinstance(parsed, dict):
            parsed = next(iter(parsed.values()), [])
        trans_map = {entry["id"]: entry["t"] for entry in parsed if "id" in entry and "t" in entry}
        translated = []
        for it in items:
            translated.append({
                "item_id"        : it["item_id"],
                "original_name"  : it["item_name"],
                "translated_name": trans_map.get(it["item_id"], it["item_name"]),
                "price"          : it["total_item_price"]
            })
        return translated
    except Exception as e:
        print(f"[Receipt] Translate fallback to original names: {e}")
        return [
            {
                "item_id"        : it["item_id"],
                "original_name"  : it["item_name"],
                "translated_name": it["item_name"],
                "price"          : it["total_item_price"]
            }
            for it in items
        ]


def parse_receipt_with_llm(raw_text: str) -> dict:
    """
    Parse hasil OCR mentah menggunakan LLM (Llama-3.1 via Groq) untuk memisahkan nama item,
    jumlah, harga, dan menghapus metadata seperti nomor meja, ID transaksi, dll.
    Jika gagal/error, fallback ke parser regex lokal.
    """
    try:
        from services.llama_service import chat_with_llama
        system_prompt = (
            "You are a receipt parsing assistant. Parse the raw OCR text of a receipt into a structured JSON object. "
            "You MUST return ONLY a JSON object matching this schema:\n"
            "{\n"
            "  \"merchant_name\": \"string or null\",\n"
            "  \"date\": \"string (YYYY-MM-DD) or null\",\n"
            "  \"currency_detected\": \"string (e.g. IDR, USD, SGD) or null\",\n"
            "  \"items\": [\n"
            "    {\n"
            "      \"item_id\": integer,\n"
            "      \"item_name\": \"string\",\n"
            "      \"quantity\": integer,\n"
            "      \"price_per_item\": integer,\n"
            "      \"total_item_price\": integer\n"
            "    }\n"
            "  ],\n"
            "  \"totals\": {\n"
            "    \"subtotal\": integer,\n"
            "    \"tax\": integer,\n"
            "    \"service_charge\": integer,\n"
            "    \"discount\": integer,\n"
            "    \"grand_total\": integer\n"
            "  }\n"
            "}\n\n"
            "Guidelines:\n"
            "1. Filter out receipt metadata (like table numbers, cashier name, reference numbers, transaction IDs, tax ID numbers, credit card numbers, WiFi passwords) from the items list.\n"
            "2. Align item names with their correct prices, especially if they are printed on separate lines. For example, if '1 Genmaicha Hot' is followed by '4,800' on the next line, they belong together as a single item with price 4800 and quantity 1.\n"
            "3. Do not include 'Subtotal', 'Tax', 'Service charge', 'PB1', or 'Total' as items in the items list. Put them in the totals object instead.\n"
            "4. For quantities, try to extract them if visible (e.g. '6 Yellow' means quantity 6, item_name 'Yellow', price_per_item is total_item_price / quantity).\n"
            "5. Convert prices to clean integers (no dots, commas, or currency symbols). If the currency is IDR, ensure the price reflects the full amount (e.g. 153,600 -> 153600).\n"
            "6. Make sure the sum of items total_item_price does not double count totals."
        )
        
        result_str = chat_with_llama(raw_text, system_prompt)
        result = json.loads(result_str)
        
        if "merchant_name" not in result:
            result["merchant_name"] = "Unknown"
        if "items" not in result:
            result["items"] = []
        if "totals" not in result:
            result["totals"] = {"subtotal": 0, "tax": 0, "service_charge": 0, "discount": 0, "grand_total": 0}
            
        return result
    except Exception as e:
        print(f"[Receipt] LLM parsing failed: {e}. Falling back to regex parser.")
        return parse_receipt_from_ocr(raw_text)


# ── Main endpoint ─────────────────────────────────────────────────────────────
@router.post("/scan")
async def scan_receipt(
    file: UploadFile = File(...),
    trip_id: Optional[str] = Form(None),
    function: ReceiptFunction = Form(ReceiptFunction.extract),
    # Split bill
    people_names: Optional[str] = Form(None, description='JSON array nama orang, contoh: ["Andi","Budi","Cici"]'),
    split_assignments: Optional[str] = Form(None, description='JSON object assignment item per orang, contoh: {"Andi":[1,2],"Budi":[3]}'),
    # Currency
    target_currency: Optional[TargetCurrency] = Form(None),
    # Translate
    target_language: Optional[TargetLanguage] = Form(None),
    current_user = Depends(_get_optional_receipt_user)
):
    try:
        image_bytes = await file.read()

        # ── STEP 1: OCR pakai PaddleOCR ──────────────────────────────────────
        try:
            raw_text = extract_text_from_image(image_bytes)
        except RuntimeError as ocr_err:
            raise HTTPException(status_code=422, detail=f"Gagal membaca gambar: {str(ocr_err)}")

        if not raw_text.strip():
            return {"error": "Struk tidak terbaca — coba foto lebih jelas"}

        print(f"[Receipt] OCR text ({len(raw_text)} chars):\n{raw_text[:400]}")

        # ── STEP 2: Parse hasil OCR → JSON (menggunakan LLM dengan fallback) ─────────
        base_result = parse_receipt_with_llm(raw_text)

        if base_result.get("error"):
            return base_result

        items  = base_result.get("items", [])
        totals = base_result.get("totals", {})

        # ── STEP 3a: Split bill ───────────────────────────────────────────────
        if function == ReceiptFunction.split_bill:
            if not people_names:
                raise HTTPException(
                    status_code=422,
                    detail='people_names wajib diisi untuk split bill. Contoh: ["Andi","Budi","Cici"]'
                )
            try:
                names_list: List[str] = json.loads(people_names)
            except Exception:
                raise HTTPException(status_code=422, detail="Format people_names tidak valid, harus JSON array string")

            currency = base_result.get("currency_detected", "IDR")

            if split_assignments:
                try:
                    assignments: dict = json.loads(split_assignments)
                except Exception:
                    raise HTTPException(status_code=422, detail="Format split_assignments tidak valid")

                subtotal = totals.get("subtotal", 0)
                tax_rate     = totals["tax"]            / subtotal if subtotal > 0 else 0
                service_rate = totals["service_charge"] / subtotal if subtotal > 0 else 0

                person_bills = {}
                for person in names_list:
                    person_item_ids = assignments.get(person, [])
                    person_items    = [it for it in items if it["item_id"] in person_item_ids]
                    person_sub      = sum(it["total_item_price"] for it in person_items)
                    person_tax      = int(person_sub * tax_rate)
                    person_service  = int(person_sub * service_rate)
                    person_total    = person_sub + person_tax + person_service

                    person_bills[person] = {
                        "items"        : person_items,
                        "subtotal"     : person_sub,
                        "tax_share"    : person_tax,
                        "service_share": person_service,
                        "total"        : person_total,
                        "currency"     : currency
                    }

                all_assigned = [iid for ids in assignments.values() for iid in ids]
                unassigned   = [it for it in items if it["item_id"] not in all_assigned]

                base_result["split_bill"] = {
                    "mode"            : "per_item_assignment",
                    "people"          : names_list,
                    "bills"           : person_bills,
                    "unassigned_items": unassigned,
                    "currency"        : currency
                }

                # Simpan ke DB
                if trip_id and current_user:
                    for person, bill in person_bills.items():
                        if bill["total"] > 0:
                            try:
                                supabase.table("expenses").insert({
                                    "user_id"    : current_user.id,
                                    "trip_id"    : trip_id,
                                    "amount"     : bill["total"],
                                    "category"   : "split_bill",
                                    "description": f"Split bill {base_result.get('merchant_name', 'Unknown')} — {person}"
                                }).execute()
                            except Exception as e:
                                print(f"[Receipt] Failed to save expense for {person}: {e}")
            else:
                base_result["split_bill"] = {
                    "mode"              : "awaiting_assignment",
                    "people"            : names_list,
                    "items_for_assignment": items,
                    "message"           : "Silakan assign item ke setiap orang, lalu kirim ulang dengan split_assignments",
                    "assignment_format" : {p: [] for p in names_list},
                    "currency"          : currency
                }

        # ── STEP 3b: Currency conversion (pure math) ─────────────────────────
        elif function == ReceiptFunction.currency:
            if not target_currency:
                raise HTTPException(status_code=422, detail="target_currency wajib dipilih untuk konversi")

            source_currency = base_result.get("currency_detected", "IDR")

            # Dapatkan rate dari exchange_service
            rate = None
            try:
                if source_currency == "IDR":
                    rate = await get_rate_from_idr(target_currency.value)
            except Exception as e:
                print(f"[Receipt] Exchange rate fetch failed: {e}")

            if rate is None or rate == 0:
                raise HTTPException(
                    status_code=502,
                    detail="Gagal mendapatkan kurs terkini. Coba lagi nanti."
                )

            def convert(amount: int) -> float:
                return round(amount * rate, 4)

            items_converted = [
                {
                    "item_id"        : it["item_id"],
                    "item_name"      : it["item_name"],
                    "original_price" : it["total_item_price"],
                    "converted_price": convert(it["total_item_price"])
                }
                for it in items
            ]

            totals_converted = {
                k: convert(v) for k, v in totals.items()
            }

            base_result["currency_conversion"] = {
                "original_currency": source_currency,
                "target_currency"  : target_currency.value,
                "exchange_rate"    : rate,
                "items_converted"  : items_converted,
                "totals_converted" : totals_converted
            }

        # ── STEP 3c: Translate (LLM hanya untuk nama item — payload minimal) ─
        elif function == ReceiptFunction.translate:
            if not target_language:
                raise HTTPException(status_code=422, detail="target_language wajib dipilih untuk terjemahan")

            translated_items = translate_items_local(items, target_language.value)

            base_result["translation"] = {
                "target_language"       : target_language.value,
                "merchant_name_translated": base_result.get("merchant_name", ""),
                "items_translated"      : translated_items
            }

        # ── STEP 4: Simpan ke expenses (extract biasa) ────────────────────────
        if function == ReceiptFunction.extract and trip_id and current_user and not base_result.get("error"):
            try:
                supabase.table("expenses").insert({
                    "user_id"    : current_user.id,
                    "trip_id"    : trip_id,
                    "amount"     : totals.get("grand_total", 0),
                    "category"   : "receipt_scan",
                    "description": f"Scan struk: {base_result.get('merchant_name', 'Unknown')}"
                }).execute()
            except Exception as e:
                print(f"[Receipt] Failed to save expense: {e}")

        return base_result

    except HTTPException:
        raise
    except Exception as e:
        print(f"[Receipt] Unexpected: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=str(e))