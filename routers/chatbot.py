from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from services.supabase_client import supabase
from services.llama_service import chat_with_llama
from middleware.auth_middleware import get_current_user
from typing import Optional

router = APIRouter()

class ChatMessage(BaseModel):
    message: str
    trip_id: Optional[str] = None

@router.post("/message")
async def chat(
    data: ChatMessage,
    current_user = Depends(get_current_user)
):
    try:
        itinerary_context = ""
        trip_context = ""

        if data.trip_id:
            # Ambil detail trip
            trip_res = supabase.table("trips")\
                .select("*")\
                .eq("id", data.trip_id)\
                .single()\
                .execute()
            if trip_res.data:
                t = trip_res.data
                trip_context = f"Destinasi: {t['destination']}, Vibe: {t['vibe']}, Budget: Rp {t['budget_min']} - Rp {t['budget_max']}"

            # Ambil itinerary aktif
            itin_res = supabase.table("itinerary_items")\
                .select("*")\
                .eq("trip_id", data.trip_id)\
                .order("day_number")\
                .order("order_index")\
                .execute()
            if itin_res.data:
                itinerary_context = str(itin_res.data)

        system_prompt = f"""
Kamu adalah Pavey, AI travel buddy yang membantu wisatawan Indonesia.
Jawab dalam Bahasa Indonesia, ramah, dan spesifik.
Berikan saran praktis dan relevan dengan perjalanan user.

{f'Info trip user: {trip_context}' if trip_context else ''}
{f'Itinerary aktif user: {itinerary_context}' if itinerary_context else ''}

Jangan jawab hal di luar konteks perjalanan wisata.
Kalau user tanya soal tempat di itinerary mereka, jawab berdasarkan data di atas.
        """

        reply = chat_with_llama(data.message, system_prompt)
        return {"reply": reply}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))