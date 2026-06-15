from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from services.supabase_client import supabase
from services.llama_service import chat_with_llama
from middleware.auth_middleware import get_current_user
from typing import Optional
from enum import Enum
import json
import re

router = APIRouter()

class ExpenseCreate(BaseModel):
    trip_id: str
    amount: int
    category: str
    description: str

class WalletCurrency(str, Enum):
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
    IDR = "IDR"

# Kurs fallback kalau LLM gagal
FALLBACK_RATES_FROM_IDR = {
    "USD": 0.000061, "EUR": 0.000057, "SGD": 0.000082,
    "MYR": 0.00029,  "JPY": 0.0091,  "KRW": 0.082,
    "AUD": 0.000094, "GBP": 0.000049, "THB": 0.0022,
    "CNY": 0.00044,  "IDR": 1.0
}

def clean_json(text: str) -> dict:
    text = re.sub(r"```json\s*|```\s*", "", text).strip()
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1:
        text = text[start:end+1]
    text = re.sub(r',\s*}', '}', text)
    text = re.sub(r',\s*]', ']', text)
    return json.loads(text)


@router.post("/expenses")
async def add_expense(
    data: ExpenseCreate,
    current_user = Depends(get_current_user)
):
    try:
        res = supabase.table("expenses").insert({
            "user_id": current_user.id,
            "trip_id": data.trip_id,
            "amount": data.amount,
            "category": data.category,
            "description": data.description
        }).execute()

        return {"message": "Expense berhasil ditambahkan", "data": res.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/expenses/{trip_id}")
async def get_expenses(
    trip_id: str,
    display_currency: Optional[WalletCurrency] = None,
    current_user = Depends(get_current_user)
):
    """
    Ambil semua expense untuk satu trip.
    Kalau display_currency diisi, total juga ditampilkan dalam currency tersebut.
    Contoh: GET /wallet/expenses/trip-id?display_currency=USD
    """
    try:
        res = supabase.table("expenses")\
            .select("*")\
            .eq("trip_id", trip_id)\
            .eq("user_id", current_user.id)\
            .order("created_at", desc=True)\
            .execute()

        total_idr = sum(item["amount"] for item in res.data)

        response = {
            "trip_id": trip_id,
            "total_spent_idr": total_idr,
            "transactions": res.data
        }

        # Konversi ke currency lain kalau diminta
        if display_currency and display_currency != WalletCurrency.IDR:
            rate = FALLBACK_RATES_FROM_IDR.get(display_currency.value, 0.000061)
            converted = round(total_idr * rate, 2)

            response["currency_display"] = {
                "target_currency": display_currency.value,
                "exchange_rate_idr": rate,
                "total_converted": converted,
                "note": "Kurs estimasi, cek kurs terkini untuk nilai akurat"
            }

        return response

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/expenses/{trip_id}/convert")
async def convert_expenses(
    trip_id: str,
    target_currency: WalletCurrency,
    current_user = Depends(get_current_user)
):
    """
    Konversi semua expense dalam satu trip ke currency target.
    Menggunakan LLM untuk kurs yang lebih akurat, dengan fallback kurs hardcoded.
    """
    try:
        res = supabase.table("expenses")\
            .select("*")\
            .eq("trip_id", trip_id)\
            .eq("user_id", current_user.id)\
            .order("created_at", desc=True)\
            .execute()

        if not res.data:
            return {
                "trip_id": trip_id,
                "target_currency": target_currency.value,
                "transactions": [],
                "total_idr": 0,
                "total_converted": 0
            }

        total_idr = sum(item["amount"] for item in res.data)

        if target_currency == WalletCurrency.IDR:
            return {
                "trip_id": trip_id,
                "target_currency": "IDR",
                "total_idr": total_idr,
                "total_converted": total_idr,
                "exchange_rate": 1.0,
                "transactions": [
                    {**item, "amount_converted": item["amount"], "currency": "IDR"}
                    for item in res.data
                ]
            }

        # Coba dapat kurs dari LLM
        currency_prompt = f"""What is the current approximate exchange rate from IDR (Indonesian Rupiah) to {target_currency.value}?
Return ONLY valid JSON, no explanation:
{{
    "from_currency": "IDR",
    "to_currency": "{target_currency.value}",
    "rate": 0.000063,
    "note": "approximate rate"
}}"""

        rate = FALLBACK_RATES_FROM_IDR.get(target_currency.value, 0.000061)
        try:
            llm_response = chat_with_llama(currency_prompt)
            rate_data = clean_json(llm_response)
            if "rate" in rate_data and isinstance(rate_data["rate"], (int, float)):
                rate = float(rate_data["rate"])
        except Exception as e:
            print(f"[Wallet] LLM rate failed, using fallback: {e}")

        # Konversi semua transaksi
        converted_transactions = []
        for item in res.data:
            converted_amount = round(item["amount"] * rate, 2)
            converted_transactions.append({
                **item,
                "amount_converted": converted_amount,
                "currency": target_currency.value
            })

        return {
            "trip_id": trip_id,
            "source_currency": "IDR",
            "target_currency": target_currency.value,
            "exchange_rate": rate,
            "total_idr": total_idr,
            "total_converted": round(total_idr * rate, 2),
            "transactions": converted_transactions,
            "note": "Kurs estimasi — cek kurs terkini untuk nilai akurat"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/expenses/{trip_id}/summary")
async def get_expense_summary(
    trip_id: str,
    current_user = Depends(get_current_user)
):
    """
    Summary pengeluaran per kategori untuk satu trip.
    Berguna untuk pie chart di frontend.
    """
    try:
        res = supabase.table("expenses")\
            .select("*")\
            .eq("trip_id", trip_id)\
            .eq("user_id", current_user.id)\
            .execute()

        if not res.data:
            return {"trip_id": trip_id, "total": 0, "by_category": {}}

        total = sum(item["amount"] for item in res.data)

        by_category = {}
        for item in res.data:
            cat = item.get("category", "other")
            if cat not in by_category:
                by_category[cat] = {"total": 0, "count": 0, "transactions": []}
            by_category[cat]["total"] += item["amount"]
            by_category[cat]["count"] += 1
            by_category[cat]["transactions"].append(item)

        # Hitung persentase per kategori
        for cat in by_category:
            by_category[cat]["percentage"] = round(
                by_category[cat]["total"] / total * 100, 1
            )

        return {
            "trip_id": trip_id,
            "total_idr": total,
            "total_transactions": len(res.data),
            "by_category": by_category
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))