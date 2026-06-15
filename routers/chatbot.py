from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from services.supabase_client import supabase
from services.llama_service import chat_with_llama
from typing import Optional
import traceback

router = APIRouter()

security = HTTPBearer(auto_error=False)  # auto_error=False = tidak throw 401 kalau tidak ada token

class ChatMessage(BaseModel):
    message: str
    trip_id: Optional[str] = None
    # Context tambahan dari frontend (itinerary lokal, destinasi, dll)
    context: Optional[str] = None

def get_optional_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    """Auth opsional — return user kalau ada token valid, None kalau tidak ada/invalid."""
    if not credentials:
        return None
    try:
        user = supabase.auth.get_user(credentials.credentials)
        if user and user.user:
            return user.user
    except Exception:
        pass
    return None


@router.post("/message")
async def chat(
    data: ChatMessage,
    current_user = Depends(get_optional_user)
):
    try:
        itinerary_context = ""
        trip_context = ""
        expense_context = ""

        # Coba load konteks dari backend kalau user login dan ada trip_id
        if current_user and data.trip_id:
            # Validasi trip_id format UUID backend
            import re
            is_backend_trip = re.match(r'^[0-9a-f-]{36}$', data.trip_id)

            if is_backend_trip:
                try:
                    trip_res = supabase.table("trips")\
                        .select("*")\
                        .eq("id", data.trip_id)\
                        .eq("user_id", current_user.id)\
                        .single()\
                        .execute()
                    if trip_res.data:
                        t = trip_res.data
                        trip_context = (
                            f"Destinasi: {t.get('destination', '-')}, "
                            f"Vibe: {t.get('vibe', '-')}, "
                            f"Budget: Rp {t.get('budget_min', 0)} - Rp {t.get('budget_max', 0)}, "
                            f"Tanggal: {t.get('start_date', '-')} s/d {t.get('end_date', '-')}"
                        )
                except Exception as e:
                    print(f"[Chatbot] Failed to load trip context: {e}")

                try:
                    itin_res = supabase.table("itinerary_items")\
                        .select("place_name, place_type, start_time, description")\
                        .eq("trip_id", data.trip_id)\
                        .order("day_number")\
                        .order("order_index")\
                        .execute()
                    if itin_res.data:
                        stops = [f"- {it.get('place_name')} ({it.get('place_type')}, {it.get('start_time', '')})" for it in itin_res.data]
                        itinerary_context = "Itinerary:\n" + "\n".join(stops)
                except Exception as e:
                    print(f"[Chatbot] Failed to load itinerary context: {e}")

                try:
                    expense_res = supabase.table("expenses")\
                        .select("amount, category, description")\
                        .eq("trip_id", data.trip_id)\
                        .eq("user_id", current_user.id)\
                        .execute()
                    if expense_res.data:
                        total = sum(e.get("amount", 0) for e in expense_res.data)
                        expense_context = f"Total pengeluaran trip: Rp {total:,} ({len(expense_res.data)} transaksi)"
                except Exception as e:
                    print(f"[Chatbot] Failed to load expense context: {e}")

        # Kalau ada context dari frontend (itinerary lokal), pakai itu
        frontend_context = data.context or ""

        user_name = ""
        if current_user:
            user_name = current_user.email.split("@")[0] if current_user.email else "Traveler"

        system_prompt = f"""Kamu adalah TinTin, AI travel buddy dari aplikasi Pavey yang membantu wisatawan.
Jawab dalam Bahasa Indonesia yang ramah, santai, dan helpful.
Berikan saran praktis, spesifik, dan relevan.
Jawab singkat tapi informatif — maksimal 3-4 kalimat kecuali diminta detail.

{f"Nama user: {user_name}" if user_name else "User belum login (mode guest)."}
{f"Info trip: {trip_context}" if trip_context else ""}
{f"{itinerary_context}" if itinerary_context else ""}
{f"Pengeluaran: {expense_context}" if expense_context else ""}
{f"Konteks dari app: {frontend_context}" if frontend_context else ""}

Fokus pada topik wisata: rekomendasi tempat, makanan, transportasi, budaya, keamanan, budget.
Kalau ditanya hal di luar travel, arahkan balik ke konteks perjalanan.
Kalau user tanya rekomendasi, berikan rekomendasi konkret dengan nama tempat spesifik.
"""

        reply = chat_with_llama(data.message, system_prompt)
        return {
            "reply": reply,
            "authenticated": current_user is not None,
            "has_trip_context": bool(trip_context or itinerary_context or frontend_context)
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[Chatbot] Error: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Chatbot error: {str(e)}")


@router.get("/health")
async def chatbot_health():
    """Health check — test koneksi ke Groq/LLM tanpa perlu auth."""
    try:
        reply = chat_with_llama("Halo, apa kabar?", "Jawab 'OK' saja.")
        return {"status": "ok", "llm_response": reply[:50]}
    except Exception as e:
        return {"status": "error", "detail": str(e)}