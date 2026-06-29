import os
import httpx
import asyncio
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from services.supabase_client import supabase
from middleware.auth_middleware import get_current_user
from datetime import date, datetime, timedelta
from typing import Optional, List
from services.google_places import enrich_place_details

router = APIRouter()

class GuestPlanRequest(BaseModel):
    city: str
    vibe: str
    budget: int
    days: int
    arrival_time: Optional[str] = "09:00"
    departure_time: Optional[str] = "14:00"
    bypass_cache: Optional[bool] = False

class EnrichRequest(BaseModel):
    places: List[str]
    city: str

class TripCreate(BaseModel):
    destination: str
    start_date: date
    end_date: date
    vibe: str
    budget_min: int
    budget_max: int

@router.post("/")
async def create_trip(
    data: TripCreate,
    current_user = Depends(get_current_user)
):
    try:
        res = supabase.table("trips").insert({
            "user_id": current_user.id,
            "destination": data.destination,
            "start_date": str(data.start_date),
            "end_date": str(data.end_date),
            "vibe": data.vibe,
            "budget_min": data.budget_min,
            "budget_max": data.budget_max,
            "status": "planning"
        }).execute()

        return {"trip_id": res.data[0]["id"], "message": "Trip berhasil dibuat"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/")
async def get_all_trips(current_user = Depends(get_current_user)):
    try:
        res = supabase.table("trips")\
            .select("*")\
            .eq("user_id", current_user.id)\
            .order("start_date", desc=True)\
            .execute()
        return {"trips": res.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{trip_id}")
async def get_trip(
    trip_id: str,
    current_user = Depends(get_current_user)
):
    try:
        res = supabase.table("trips")\
            .select("*")\
            .eq("id", trip_id)\
            .eq("user_id", current_user.id)\
            .single()\
            .execute()
        return res.data
    except Exception as e:
        raise HTTPException(status_code=404, detail="Trip tidak ditemukan")

@router.get("/{trip_id}/itinerary")
async def get_itinerary(
    trip_id: str,
    current_user = Depends(get_current_user)
):
    try:
        res = supabase.table("itinerary_items")\
            .select("*")\
            .eq("trip_id", trip_id)\
            .order("day_number")\
            .order("order_index")\
            .execute()

        days = {}
        for item in res.data:
            day = str(item["day_number"])
            if day not in days:
                days[day] = []
            days[day].append(item)

        return {"trip_id": trip_id, "itinerary": days}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class SaveItineraryItem(BaseModel):
    day_number: int
    order_index: int
    place_name: str
    place_type: str
    start_time: str
    end_time: str
    travel_time_to_next: int
    notes: str

@router.post("/{trip_id}/itinerary")
async def save_itinerary(
    trip_id: str,
    data: List[SaveItineraryItem],
    current_user = Depends(get_current_user)
):
    try:
        # Check if the trip exists and belongs to the user
        trip = supabase.table("trips")\
            .select("id")\
            .eq("id", trip_id)\
            .eq("user_id", current_user.id)\
            .single()\
            .execute()
        if not trip.data:
            raise HTTPException(status_code=404, detail="Trip tidak ditemukan")

        # Delete existing itinerary items
        supabase.table("itinerary_items")\
            .delete()\
            .eq("trip_id", trip_id)\
            .execute()

        # Insert new itinerary items
        items_to_insert = []
        for item in data:
            items_to_insert.append({
                "trip_id": trip_id,
                "day_number": item.day_number,
                "order_index": item.order_index,
                "place_name": item.place_name,
                "place_type": item.place_type,
                "start_time": item.start_time,
                "end_time": item.end_time,
                "travel_time_to_next": item.travel_time_to_next,
                "notes": item.notes,
            })

        if items_to_insert:
            supabase.table("itinerary_items").insert(items_to_insert).execute()

        # Also update the trip status to 'generated' so we know it has an itinerary
        supabase.table("trips")\
            .update({"status": "generated"})\
            .eq("id", trip_id)\
            .execute()

        return {"message": "Itinerary berhasil disimpan", "trip_id": trip_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def enrich_itinerary_items(itinerary_list: list, city: str):
    if not itinerary_list:
        return
    tasks = []
    for item in itinerary_list:
        name = item.get("name")
        if name:
            tasks.append(enrich_place_details(name, city))
        else:
            tasks.append(asyncio.sleep(0, result={}))
    results = await asyncio.gather(*tasks)
    for item, enrichment in zip(itinerary_list, results):
        if enrichment:
            item["image"] = enrichment.get("image") or item.get("image")
            item["cost"] = enrichment.get("cost") if enrichment.get("cost") is not None else item.get("cost", 0)
            if enrichment.get("rating"):
                item["rating"] = enrichment.get("rating")
            if enrichment.get("total_reviews"):
                item["total_reviews"] = enrichment.get("total_reviews")
            if enrichment.get("latitude") is not None:
                item["latitude"] = enrichment.get("latitude")
            if enrichment.get("longitude") is not None:
                item["longitude"] = enrichment.get("longitude")

@router.post("/enrich-places")
async def enrich_places(data: EnrichRequest):
    try:
        tasks = []
        for name in data.places:
            if name:
                tasks.append(enrich_place_details(name, data.city))
            else:
                tasks.append(asyncio.sleep(0, result={}))
        results = await asyncio.gather(*tasks)
        
        response_data = []
        for name, res in zip(data.places, results):
            item = {
                "name": name,
                "image": res.get("image"),
                "rating": res.get("rating"),
                "cost": res.get("cost"),
                "latitude": res.get("latitude"),
                "longitude": res.get("longitude")
            }
            response_data.append(item)
            
        return {"results": response_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/generate-plan")
async def generate_guest_plan(data: GuestPlanRequest):
    try:
        ai_core_url = os.getenv("AI_CORE_URL", "http://localhost:8080")
        all_itinerary_list = []
        current_date = datetime.now()
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                exclude_names = []
                for day in range(1, data.days + 1):
                    start_datetime_str = f"{current_date.strftime('%Y-%m-%d')}T{data.arrival_time}:00"
                    payload = {
                        "city": data.city,
                        "preference": data.vibe,
                        "num_places": 4 if day > 1 else 5,
                        "start_datetime": start_datetime_str,
                        "duration_per_place": [60],
                        "place_type": "all",
                        "bypass_cache": data.bypass_cache,
                        "exclude_names": exclude_names
                    }
                    ai_response = await client.post(
                        f"{ai_core_url}/api/v1/generate-itinerary",
                        json=payload
                    )
                    if ai_response.status_code != 200:
                        raise RuntimeError(f"AI Core status code {ai_response.status_code}: {ai_response.text}")
                    
                    day_data = ai_response.json()
                    day_itin = day_data.get("itinerary", [])
                    for item in day_itin:
                        item["day_number"] = day
                        if item.get("name"):
                            exclude_names.append(item["name"])
                    
                    all_itinerary_list.extend(day_itin)
                    current_date += timedelta(days=1)
            
            # Enrich details from Google Places
            await enrich_itinerary_items(all_itinerary_list, data.city)
        except Exception as api_err:
            print(f"[Trips API] AI Core connection failed or returned error: {api_err}. Running LLM fallback...")
            all_itinerary_list = generate_fallback_itinerary(data.city, data.vibe, data.days, data.arrival_time)

        return {
            "status": "success",
            "city": data.city,
            "itinerary": all_itinerary_list
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{trip_id}/generate")
async def generate_itinerary(
    trip_id: str,
    current_user = Depends(get_current_user)
):
    try:
        trip = supabase.table("trips")\
            .select("*")\
            .eq("id", trip_id)\
            .eq("user_id", current_user.id)\
            .single()\
            .execute()

        if not trip.data:
            raise HTTPException(status_code=404, detail="Trip tidak ditemukan")

        t = trip.data
        ai_core_url = os.getenv("AI_CORE_URL", "http://localhost:8080")

        # Parse start and end date to get number of days
        start_date = datetime.strptime(t["start_date"], "%Y-%m-%d")
        end_date = datetime.strptime(t["end_date"], "%Y-%m-%d")
        num_days = (end_date - start_date).days + 1
        num_days = max(1, min(num_days, 10)) # clamp to dynamic range

        all_itinerary_list = []
        weather_modes = []
        current_date = start_date

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                exclude_names = []
                for day in range(1, num_days + 1):
                    start_datetime_str = f"{current_date.strftime('%Y-%m-%d')}T09:00:00"
                    payload = {
                        "city": t["destination"],
                        "preference": t["vibe"],
                        "num_places": 4 if day > 1 else 5,
                        "start_datetime": start_datetime_str,
                        "duration_per_place": [60],
                        "place_type": "all",
                        "exclude_names": exclude_names
                    }
                    ai_response = await client.post(
                        f"{ai_core_url}/api/v1/generate-itinerary",
                        json=payload
                    )
                    if ai_response.status_code != 200:
                        raise RuntimeError(f"AI Core status code {ai_response.status_code}: {ai_response.text}")
                    
                    day_data = ai_response.json()
                    day_itin = day_data.get("itinerary", [])
                    for item in day_itin:
                        item["day_number"] = day
                        if item.get("name"):
                            exclude_names.append(item["name"])
                    all_itinerary_list.extend(day_itin)
                    if day_data.get("weather_mode"):
                        weather_modes.append(day_data["weather_mode"])
                    current_date += timedelta(days=1)
            
            # Enrich details from Google Places
            await enrich_itinerary_items(all_itinerary_list, t["destination"])
        except Exception as api_err:
            print(f"[Trips API] AI Core connection failed or returned error: {api_err}. Running LLM fallback...")
            all_itinerary_list = generate_fallback_itinerary(t["destination"], t["vibe"], num_days, "09:00")

        supabase.table("itinerary_items")\
            .delete()\
            .eq("trip_id", trip_id)\
            .execute()

        items_to_insert = []
        for item in all_itinerary_list:
            # Calculate end_time from start_time + duration
            start_time_str = item.get("arrival_time", "09:00")
            duration_min = item.get("duration_spent_minutes", 60)
            try:
                from datetime import datetime, timedelta
                st = datetime.strptime(start_time_str, "%H:%M")
                et = (st + timedelta(minutes=duration_min)).strftime("%H:%M")
            except Exception:
                et = start_time_str

            # Store rich metadata (lat/lng, rating, activity) in notes as JSON
            import json as _json
            notes_data = _json.dumps({
                "activity": item.get("activity_todo", ""),
                "latitude": item.get("latitude"),
                "longitude": item.get("longitude"),
                "rating": item.get("rating"),
                "total_reviews": item.get("total_reviews"),
                "duration_minutes": duration_min,
                "image": item.get("image"),
                "cost": item.get("cost", 0),
            })

            items_to_insert.append({
                "trip_id": trip_id,
                "day_number": item.get("day_number", 1),
                "order_index": item.get("step", 0),
                "place_name": item.get("name", ""),
                "place_type": item.get("type", "destination"),
                "start_time": start_time_str,
                "end_time": et,
                "travel_time_to_next": item.get("travel_time_to_next_minutes", 0),
                "notes": notes_data,
            })

        if items_to_insert:
            supabase.table("itinerary_items").insert(items_to_insert).execute()

        supabase.table("trips")\
            .update({"status": "generated"})\
            .eq("id", trip_id)\
            .execute()

        return {
            "message": "Itinerary berhasil digenerate",
            "trip_id": trip_id,
            "weather_mode": weather_modes[0] if weather_modes else "Standard (Clear)",
            "itinerary": all_itinerary_list
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{trip_id}/complete")
async def complete_trip(
    trip_id: str,
    current_user = Depends(get_current_user)
):
    """
    Dipanggil setelah user selesai trip.
    Simpan preferensi user ke tabel user_preferences untuk personalisasi berikutnya.
    """
    try:
        # Ambil data trip
        trip = supabase.table("trips")\
            .select("*")\
            .eq("id", trip_id)\
            .eq("user_id", current_user.id)\
            .single()\
            .execute()

        if not trip.data:
            raise HTTPException(status_code=404, detail="Trip tidak ditemukan")

        t = trip.data

        # Ambil semua tempat yang dikunjungi
        items = supabase.table("itinerary_items")\
            .select("place_name, place_type")\
            .eq("trip_id", trip_id)\
            .execute()

        visited_places = [item["place_name"] for item in items.data]

        # Cek apakah user sudah punya preferences sebelumnya
        existing = supabase.table("user_preferences")\
            .select("id, vibe_history")\
            .eq("user_id", current_user.id)\
            .execute()

        # Gabungkan vibe baru dengan data preferences yang ada
        vibe_history = {"vibes": [t["vibe"]], "chats": {}}
        if existing.data and existing.data[0].get("vibe_history"):
            existing_vh = existing.data[0]["vibe_history"]
            if isinstance(existing_vh, dict):
                if "chats" in existing_vh or "vibes" in existing_vh:
                    vibe_history["chats"] = existing_vh.get("chats") or {}
                    existing_vibes = existing_vh.get("vibes") or []
                    if isinstance(existing_vibes, list):
                        vibe_history["vibes"] = list(set(existing_vibes + [t["vibe"]]))
                    else:
                        vibe_history["vibes"] = [t["vibe"]]
                else:
                    vibe_history["chats"] = existing_vh
                    vibe_history["vibes"] = [t["vibe"]]
            elif isinstance(existing_vh, list):
                vibe_history["vibes"] = list(set(existing_vh + [t["vibe"]]))

        pref_data = {
            "user_id": current_user.id,
            "vibe_history": vibe_history,
            "budget_min": int(t["budget_min"]) if isinstance(t["budget_min"], (int, float, str)) and str(t["budget_min"]).isdigit() else 0,
            "budget_max": int(t["budget_max"]) if isinstance(t["budget_max"], (int, float, str)) and str(t["budget_max"]).isdigit() else 0,
            "destination_type": t.get("destination_type", "mixed"),
            "visited_places": visited_places,
            "updated_at": "now()"
        }

        # Gunakan upsert dengan on_conflict="user_id" untuk menyederhanakan insert/update
        supabase.table("user_preferences")\
            .upsert(pref_data, on_conflict="user_id")\
            .execute()

        # Update status trip jadi completed
        supabase.table("trips")\
            .update({"status": "completed"})\
            .eq("id", trip_id)\
            .execute()

        return {
            "message": "Trip selesai, preferensi berhasil disimpan",
            "trip_id": trip_id,
            "preferences_saved": {
                "vibe": t["vibe"],
                "budget_range": f"Rp {t['budget_min']} - Rp {t['budget_max']}",
                "places_visited": len(visited_places)
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/preferences/history")
async def get_user_preferences(
    current_user = Depends(get_current_user)
):
    try:
        prefs = supabase.table("user_preferences")\
            .select("vibe_history, budget_min, budget_max, destination_type, visited_places, updated_at")\
            .eq("user_id", current_user.id)\
            .single()\
            .execute()

        if not prefs.data:
            return {
                "has_history": False,
                "message": "Belum ada histori preferensi"
            }

        p = prefs.data
        vibe_list = []
        vh = p.get("vibe_history")
        if isinstance(vh, dict):
            vibe_list = vh.get("vibes") or []
        elif isinstance(vh, list):
            vibe_list = vh
            
        vibe = vibe_list[-1] if vibe_list else None

        # Return format expected by caller
        return {
            "has_history": True,
            "preferences": {
                "vibe": vibe,
                "budget_min": p.get("budget_min"),
                "budget_max": p.get("budget_max"),
                "destination_type": p.get("destination_type"),
                "visited_places": p.get("visited_places") or [],
                "updated_at": p.get("updated_at")
            }
        }

    except Exception as e:
        return {"has_history": False, "message": f"Belum ada histori preferensi: {str(e)}"}


def generate_fallback_itinerary(city: str, vibe: str, days: int, start_time: str = "09:00") -> list:
    import json
    import re
    from services.llama_service import chat_with_llama
    
    prompt = f"""You are a travel itinerary expert. Create a {days}-day itinerary for {city} with a {vibe} vibe.

CRITICAL RULES:
- Use REAL, SPECIFIC, WELL-KNOWN place names that actually exist in {city}. 
- Do NOT use generic names like "City Park", "Local Cuisine", "History Museum", or templates like "Museum of {city}".
- Include famous landmarks, popular restaurants, and known attractions specific to {city}.
- Coordinates MUST be accurate for {city}. Do not use default 0,0 values.
- Each day should have 4 places: morning attraction, lunch spot, afternoon attraction, dinner spot.

Return ONLY a valid JSON object in this exact format, no other text:
{{
    "itinerary": [
        {{
            "name": "Exact real place name specific to the requested city (e.g. 'Gedung Sate' for Bandung, 'Monas' for Jakarta, 'Borobudur' for Yogyakarta)",
            "type": "destination|restaurant|attraction",
            "price": 50000,
            "rating": 4.5,
            "latitude": 0.0,
            "longitude": 0.0,
            "activity_todo": "Specific activity description",
            "duration_spent_minutes": 90,
            "travel_time_to_next_minutes": 20,
            "arrival_time": "09:00",
            "step": 1,
            "day_number": 1
        }}
    ]
}}
"""
    try:
        # Scale max_tokens dynamically based on number of days (800 tokens/day, min 2048, max 8192) to prevent JSON truncation
        max_tokens = min(8192, max(2048, days * 800))
        reply = chat_with_llama(
            message=prompt,
            system_prompt="You are a travel itinerary expert. Respond only with a single valid JSON block.",
            max_tokens=max_tokens
        )
        clean_reply = reply.strip()
        if "```" in clean_reply:
            match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', clean_reply)
            if match:
                clean_reply = match.group(1).strip()
        
        data = json.loads(clean_reply)
        items = data.get("itinerary") or []
        
        # Format sekuensial jika ada info yang kurang
        for day in range(1, days + 1):
            day_items = [it for it in items if it.get("day_number") == day]
            if not day_items:
                continue
            
            cursor_min = 9 * 60  # start at 09:00
            for idx, item in enumerate(day_items):
                item["step"] = idx + 1
                if "arrival_time" not in item:
                    h = cursor_min // 60
                    m = cursor_min % 60
                    item["arrival_time"] = f"{h:02d}:{m:02d}"
                duration = item.get("duration_spent_minutes", 60)
                travel = item.get("travel_time_to_next_minutes", 15)
                cursor_min += duration + travel
                
        return items
    except Exception as e:
        raw_snippet = reply[:300] if 'reply' in locals() else 'None'
        print(f"[Fallback Planner] Error: {e}. Raw reply snippet: {raw_snippet}")
        print("[Fallback Planner] Using safety mock data.")
        items = []
        for d in range(1, days + 1):
            times = ["09:00", "12:00", "15:00", "18:00"]
            names = ["Taman Kota", "Kuliner Khas", "Museum Sejarah", "Restoran Malam"]
            types = ["destination", "restaurant", "attraction", "restaurant"]
            for idx in range(4):
                items.append({
                    "name": f"{names[idx]} {city}",
                    "type": types[idx],
                    "price": 0,
                    "rating": 4.5,
                    "latitude": -6.2 + (idx * 0.005),
                    "longitude": 106.8 + (idx * 0.005),
                    "activity_todo": f"Mengunjungi dan menikmati {names[idx]}",
                    "duration_spent_minutes": 60 if types[idx] == "restaurant" else 90,
                    "travel_time_to_next_minutes": 15,
                    "arrival_time": times[idx],
                    "step": idx + 1,
                    "day_number": d
                })
        return items