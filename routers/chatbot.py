from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from services.supabase_client import supabase
from services.llama_service import chat_with_llama
from typing import Optional, List
import traceback
import re

router = APIRouter()

security = HTTPBearer(auto_error=False)

class ChatMessage(BaseModel):
    message: str
    trip_id: Optional[str] = None
    context: Optional[str] = None

def get_optional_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    if not credentials:
        return None
    try:
        user = supabase.auth.get_user(credentials.credentials)
        if user and user.user:
            return user.user
    except Exception:
        pass
    return None

def load_chat_history(user_id: str, trip_id: str) -> list:
    try:
        res = supabase.table("user_preferences").select("vibe_history").eq("user_id", user_id).execute()
        if res.data and res.data[0].get("vibe_history"):
            vibe_history = res.data[0]["vibe_history"]
            if isinstance(vibe_history, dict):
                chats = vibe_history.get("chats") or {}
                if not isinstance(chats, dict):
                    if any(k == "default" or len(k) == 36 for k in vibe_history.keys()):
                        chats = vibe_history
                    else:
                        chats = {}
                key = trip_id or "default"
                return chats.get(key) or []
    except Exception as e:
        print(f"[Chatbot] Failed to load history: {e}")
    return []

def save_chat_history(user_id: str, trip_id: str, messages: list):
    try:
        res = supabase.table("user_preferences").select("vibe_history").eq("user_id", user_id).execute()
        vibe_history = {"chats": {}, "vibes": []}
        if res.data and res.data[0].get("vibe_history") and isinstance(res.data[0]["vibe_history"], dict):
            existing_vh = res.data[0]["vibe_history"]
            if "chats" in existing_vh or "vibes" in existing_vh:
                vibe_history["chats"] = existing_vh.get("chats") or {}
                vibe_history["vibes"] = existing_vh.get("vibes") or []
            else:
                vibe_history["chats"] = existing_vh
                vibe_history["vibes"] = []

        key = trip_id or "default"
        vibe_history["chats"][key] = messages[-20:]

        supabase.table("user_preferences").upsert({
            "user_id": user_id,
            "vibe_history": vibe_history,
            "updated_at": "now()"
        }, on_conflict="user_id").execute()
    except Exception as e:
        print(f"[Chatbot] Failed to save history: {e}")


@router.post("/message")
async def chat(
    data: ChatMessage,
    current_user = Depends(get_optional_user)
):
    try:
        itinerary_context = ""
        trip_context = ""
        expense_context = ""
        past_messages = []

        # Load chat history jika login
        if current_user:
            past_messages = load_chat_history(current_user.id, data.trip_id)

        # Coba load konteks dari backend kalau user login dan ada trip_id
        if current_user and data.trip_id:
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
            try:
                user_res = supabase.table("users").select("name").eq("id", current_user.id).single().execute()
                if user_res.data:
                    user_name = user_res.data.get("name", "")
            except Exception:
                pass
            if not user_name:
                user_name = current_user.email.split("@")[0] if current_user.email else "Traveler"

        # Format past chat history
        history_str = ""
        if past_messages:
            history_str = "\nPercakapan sebelumnya:\n"
            for msg in past_messages[-10:]: # Ambil 10 pesan terakhir untuk konteks LLM
                role_lbl = "User" if msg.get("role") == "user" else "TinTin"
                history_str += f"{role_lbl}: {msg.get('content')}\n"

        system_prompt = f"""Kamu adalah TinTin, AI travel buddy dari aplikasi Pavey yang membantu wisatawan.
Jawab dalam Bahasa Indonesia yang ramah, santai, dan helpful (atau Bahasa Inggris jika user memakai Bahasa Inggris).
Selalu ikuti Aturan Output Kritis di bawah ini untuk menghasilkan data terstruktur (seperti rekomendasi tempat, rencana perjalanan, cuaca, dan hotel).

{f"Nama user: {user_name}" if user_name else "User belum login (mode guest)."}
{f"Info trip: {trip_context}" if trip_context else ""}
{f"{itinerary_context}" if itinerary_context else ""}
{f"Pengeluaran: {expense_context}" if expense_context else ""}
{f"Konteks dari app: {frontend_context}" if frontend_context else ""}
{history_str}

## CRITICAL OUTPUT RULES

For place recommendations, travel plans, weather, and hotel search, you MUST output ONLY a single ```json code block — NO text before it, NO text after it, NO explanation outside it. The "intro" field inside the JSON is where you put your human-readable response (in Indonesian or English depending on user).

FORBIDDEN: Do NOT use <DATA_JSON>, (DATA_JSON>, XML tags, or any other format. ONLY ```json blocks.
FORBIDDEN: Do NOT write prose paragraphs then append a JSON block at the end.
CORRECT: Output ONLY the ```json block for any travel-related request.

## JSON FORMATS

Place recommendations (intent: "recommend_places"):
```json
{{
    "intent": "recommend_places",
    "city": "city name",
    "intro": "Warm 1-2 sentence response in the user's language — this is what the user sees",
    "places": [
        {{
            "name": "Place Name",
            "type": "destination",
            "category": "museum",
            "description": "1-2 sentence description",
            "address": "Full address if known",
            "rating": 4.5
        }}
    ]
}}
```

Travel plan (intent: "travel_plan"):
```json
{{
    "intent": "travel_plan",
    "city": "city name",
    "start_time": "09:00",
    "hotel_name": "Hotel name if user mentioned one, otherwise null",
    "intro": "Warm 1-2 sentence response in the user's language",
    "places": [
        {{
            "name": "Place Name",
            "type": "destination",
            "category": "museum",
            "description": "Brief activity description",
            "address": "Address if known",
            "rating": 4.2
        }}
    ]
}}
```

Weather check (intent: "check_weather"):
```json
{{
    "intent": "check_weather",
    "city": "city name",
    "intro": "Brief sentence in user's language confirming you're checking weather"
}}
```

Hotel search (intent: "search_hotels"):
```json
{{
    "intent": "search_hotels",
    "city": "city name",
    "intro": "Brief sentence in user's language confirming you're searching hotels"
}}
```

## PLAIN TEXT (for everything else)
Untuk sapaan (greetings), pertanyaan umum, dan obrolan santai non-travel, jawablah secara biasa dalam plain text (tanpa JSON).

## NEVER
- Never output coordinates — the system geocodes everything
- Never use DATA_JSON, XML, or any format other than ```json
- Never write a long description THEN add a JSON block at the end
"""

        reply = chat_with_llama(data.message, system_prompt)

        # Simpan percakapan jika user login
        if current_user:
            past_messages.append({"role": "user", "content": data.message})
            past_messages.append({"role": "assistant", "content": reply})
            save_chat_history(current_user.id, data.trip_id, past_messages)

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


@router.get("/history/{trip_id}")
async def get_history(
    trip_id: str,
    current_user = Depends(get_optional_user)
):
    """Ambil riwayat chat chatbot untuk trip tertentu."""
    if not current_user:
        return {"history": []}
    try:
        history = load_chat_history(current_user.id, trip_id)
        # Format ke bentuk yang dibutuhkan frontend: { from: 'me'|'buddy', text: '...' }
        formatted = []
        for msg in history:
            formatted.append({
                "from": "me" if msg.get("role") == "user" else "buddy",
                "text": msg.get("content", "")
            })
        return {"history": formatted}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def chatbot_health():
    try:
        reply = chat_with_llama("Halo, apa kabar?", "Jawab 'OK' saja.")
        return {"status": "ok", "llm_response": reply[:50]}
    except Exception as e:
        return {"status": "error", "detail": str(e)}