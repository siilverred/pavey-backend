from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from services.supabase_client import supabase
from services.gemini_service import analyze_image
from services.llama_service import chat_with_llama
from services.exchange_service import get_rate_from_idr
from middleware.auth_middleware import get_current_user
from typing import Optional, List
from enum import Enum
import json
import re

router = APIRouter()


# ── Enums untuk dropdown di Swagger ────────────────────────────────────────
class ReceiptFunction(str, Enum):
    extract = "extract"
    split_bill = "split_bill"
    currency = "currency"
    translate = "translate"

class TargetCurrency(str, Enum):
    USD = "USD"
    EUR = "EUR"
    SGD = "SGD"
    MYR = "MYR"
    JPY = "JPY"
    KRW = "KRW"
    AUD = "AUD"
    GBP = "GBP"
    THB = "THB"
    CNY = "CNY"

class TargetLanguage(str, Enum):
    english = "English"
    japanese = "Japanese"
    korean = "Korean"
    mandarin = "Mandarin Chinese"
    malay = "Malay"
    thai = "Thai"
    arabic = "Arabic"
    french = "French"


# ── JSON cleaner ────────────────────────────────────────────────────────────
def clean_json_string(text: str) -> str:
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    text = text.strip()

    # Brace-matching: ambil JSON object pertama yang valid
    start = text.find('{')
    if start != -1:
        depth = 0
        for i, ch in enumerate(text[start:], start):
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    text = text[start:i+1]
                    break

    text = re.sub(r',\s*}', '}', text)
    text = re.sub(r',\s*]', ']', text)

    # Hapus ribuan separator: 177,500 → 177500
    prev = None
    while prev != text:
        prev = text
        text = re.sub(r'(?<=\d),(?=\d{3}(?:[^\d]|$))', '', text)

    text = re.sub(r"(?<![\\])'([^']*)'(?=\s*:)", r'"\1"', text)
    return text


def try_parse_json(text: str) -> dict:
    clean = clean_json_string(text)

    # Attempt 1: json.loads
    try:
        return json.loads(clean)
    except json.JSONDecodeError as e:
        print(f"[Receipt] json.loads failed: {e}")

    # Attempt 2: ast.literal_eval
    try:
        import ast
        return ast.literal_eval(clean)
    except Exception as e:
        print(f"[Receipt] ast.literal_eval failed: {e}")

    # Attempt 3: aggressive digit-comma strip
    try:
        aggressive = re.sub(r'(\d),(\d)', r'\1\2', clean)
        return json.loads(aggressive)
    except Exception as e:
        print(f"[Receipt] All parse attempts failed: {e}")
        raise HTTPException(
            status_code=422,
            detail="Gagal membaca struk — coba foto lebih jelas atau pencahayaan lebih baik"
        )


def safe_int(value) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        cleaned = value.replace(",", "").replace(".", "").strip()
        return int(float(cleaned)) if cleaned else 0
    return 0


# ── Main endpoint ───────────────────────────────────────────────────────────
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
    current_user = Depends(get_current_user)
):
    try:
        image_bytes = await file.read()

        # ── STEP 1: Extract receipt (selalu dilakukan dulu) ─────────────────
        extract_prompt = """You are a precise receipt OCR system for a financial management app.
Extract ALL items from this receipt image into a strict JSON format.
Return ONLY valid JSON. No explanation, no markdown, no code blocks.

CRITICAL NUMBER RULES:
- NO thousand separators: write 177500 NOT 177,500
- NO currency symbols in numbers
- All prices as plain integers

Required format:
{
    "merchant_name": "store name",
    "date": "YYYY-MM-DD or null",
    "currency_detected": "IDR",
    "items": [
        {
            "item_id": 1,
            "item_name": "exact item name from receipt",
            "quantity": 1,
            "price_per_item": 50000,
            "total_item_price": 50000
        }
    ],
    "totals": {
        "subtotal": 0,
        "tax": 0,
        "service_charge": 0,
        "discount": 0,
        "grand_total": 0
    }
}

Rules:
- item_id starts from 1, sequential, used for split bill checkbox mapping
- Separate EVERY item individually, never combine different items
- subtotal = sum of all total_item_price
- grand_total = final amount paid
- If receipt cannot be read: {"error": "Struk tidak terbaca"}"""

        result_text = await analyze_image(image_bytes, extract_prompt)
        print(f"[Receipt] Raw OCR response: {repr(result_text)}")

        base_result = try_parse_json(result_text)

        if base_result.get("error"):
            return base_result

        # Normalize semua angka
        for item in base_result.get("items", []):
            item["price_per_item"] = safe_int(item.get("price_per_item", 0))
            item["total_item_price"] = safe_int(item.get("total_item_price", 0))
            item["quantity"] = int(item.get("quantity", 1))

        totals = base_result.get("totals", {})
        for key in ["subtotal", "tax", "service_charge", "discount", "grand_total"]:
            totals[key] = safe_int(totals.get(key, 0))
        base_result["totals"] = totals

        # ── STEP 2: Split bill ──────────────────────────────────────────────
        if function == ReceiptFunction.split_bill:
            if not people_names:
                raise HTTPException(
                    status_code=422,
                    detail="people_names wajib diisi untuk split bill. Contoh: [\"Andi\",\"Budi\",\"Cici\"]"
                )

            try:
                names_list: List[str] = json.loads(people_names)
            except Exception:
                raise HTTPException(status_code=422, detail="Format people_names tidak valid, harus JSON array string")

            items = base_result.get("items", [])
            currency = base_result.get("currency_detected", "IDR")

            # Kalau ada assignments (user sudah centang item), proses langsung
            if split_assignments:
                try:
                    assignments: dict = json.loads(split_assignments)
                except Exception:
                    raise HTTPException(status_code=422, detail="Format split_assignments tidak valid")

                # Hitung per orang berdasarkan item yang mereka centang
                tax_rate = totals["tax"] / totals["subtotal"] if totals["subtotal"] > 0 else 0
                service_rate = totals["service_charge"] / totals["subtotal"] if totals["subtotal"] > 0 else 0

                person_bills = {}
                for person in names_list:
                    person_item_ids = assignments.get(person, [])
                    person_items = [it for it in items if it["item_id"] in person_item_ids]
                    person_subtotal = sum(it["total_item_price"] for it in person_items)
                    person_tax = int(person_subtotal * tax_rate)
                    person_service = int(person_subtotal * service_rate)
                    person_total = person_subtotal + person_tax + person_service

                    person_bills[person] = {
                        "items": person_items,
                        "subtotal": person_subtotal,
                        "tax_share": person_tax,
                        "service_share": person_service,
                        "total": person_total,
                        "currency": currency
                    }

                # Item yang tidak di-assign siapapun
                all_assigned_ids = [iid for ids in assignments.values() for iid in ids]
                unassigned = [it for it in items if it["item_id"] not in all_assigned_ids]

                base_result["split_bill"] = {
                    "mode": "per_item_assignment",
                    "people": names_list,
                    "bills": person_bills,
                    "unassigned_items": unassigned,
                    "currency": currency
                }

                # Simpan expense per orang ke DB kalau ada trip_id
                if trip_id:
                    for person, bill in person_bills.items():
                        if bill["total"] > 0:
                            try:
                                supabase.table("expenses").insert({
                                    "user_id": current_user.id,
                                    "trip_id": trip_id,
                                    "amount": bill["total"],
                                    "category": "split_bill",
                                    "description": f"Split bill {base_result.get('merchant_name', 'Unknown')} — {person}"
                                }).execute()
                            except Exception as e:
                                print(f"[Receipt] Failed to save expense for {person}: {e}")

            else:
                # Belum ada assignments — return items untuk frontend tampilkan checkbox
                base_result["split_bill"] = {
                    "mode": "awaiting_assignment",
                    "people": names_list,
                    "items_for_assignment": items,
                    "message": "Silakan assign item ke setiap orang, lalu kirim ulang dengan split_assignments",
                    "assignment_format": {p: [] for p in names_list},
                    "currency": currency
                }

        # ── STEP 3: Currency conversion ─────────────────────────────────────
        elif function == ReceiptFunction.currency:
            if not target_currency:
                raise HTTPException(status_code=422, detail="target_currency wajib dipilih untuk konversi")

            source_currency = base_result.get("currency_detected", "IDR")
            items = base_result.get("items", [])

            # Coba dapat kurs real-time dari API jika asalnya IDR
            rate = await get_rate_from_idr(target_currency.value) if source_currency == "IDR" else None
            rate_hint = f"Use EXACTLY this exchange rate: {rate} for the conversion. All converted prices MUST equal original_price * {rate}." if rate is not None else "Use realistic current exchange rates."

            currency_prompt = f"""You are a currency converter.
Convert prices from {source_currency} to {target_currency.value}.
{rate_hint}
Return ONLY valid JSON, no explanation, no markdown, no thousand separators in numbers.""",StartLine:275,TargetContent:

Receipt data to convert:
{json.dumps({"currency": source_currency, "items": items, "totals": totals})}

Required format:
{{
    "original_currency": "{source_currency}",
    "target_currency": "{target_currency.value}",
    "exchange_rate": 0.000063,
    "items_converted": [
        {{
            "item_id": 1,
            "item_name": "item name",
            "original_price": 50000,
            "converted_price": 3.15
        }}
    ],
    "totals_converted": {{
        "subtotal": 0,
        "tax": 0,
        "service_charge": 0,
        "discount": 0,
        "grand_total": 0
    }}
}}"""

            currency_text = chat_with_llama(currency_prompt)
            print(f"[Receipt] Currency raw: {repr(currency_text)}")

            try:
                currency_result = try_parse_json(currency_text)
                base_result["currency_conversion"] = currency_result
            except Exception as e:
                print(f"[Receipt] Currency parse failed: {e}")
                base_result["currency_conversion"] = {
                    "error": "Konversi gagal, coba lagi",
                    "original_currency": source_currency,
                    "target_currency": target_currency.value
                }

        # ── STEP 4: Translate ───────────────────────────────────────────────
        elif function == ReceiptFunction.translate:
            if not target_language:
                raise HTTPException(status_code=422, detail="target_language wajib dipilih untuk terjemahan")

            items = base_result.get("items", [])

            translate_prompt = f"""You are a menu translator.
Translate ALL item names from the receipt to {target_language.value}.
Keep item_id the same.
Return ONLY valid JSON, no explanation, no markdown.

Items to translate:
{json.dumps(items)}

Required format:
{{
    "target_language": "{target_language.value}",
    "merchant_name_translated": "translated merchant name",
    "items_translated": [
        {{
            "item_id": 1,
            "original_name": "original item name",
            "translated_name": "translated name",
            "price": 50000
        }}
    ]
}}"""

            translate_text = chat_with_llama(translate_prompt)
            print(f"[Receipt] Translate raw: {repr(translate_text)}")

            try:
                translate_result = try_parse_json(translate_text)
                base_result["translation"] = translate_result
            except Exception as e:
                print(f"[Receipt] Translate parse failed: {e}")
                base_result["translation"] = {
                    "error": "Terjemahan gagal, coba lagi",
                    "target_language": target_language.value
                }

        # ── STEP 5: Simpan ke expenses (extract biasa) ──────────────────────
        if function == ReceiptFunction.extract and trip_id and not base_result.get("error"):
            try:
                supabase.table("expenses").insert({
                    "user_id": current_user.id,
                    "trip_id": trip_id,
                    "amount": totals.get("grand_total", 0),
                    "category": "receipt_scan",
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