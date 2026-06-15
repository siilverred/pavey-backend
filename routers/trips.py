import os
import httpx
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from services.supabase_client import supabase
from middleware.auth_middleware import get_current_user
from datetime import date, datetime
from typing import Optional

router = APIRouter()

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

        # Bangun start_datetime dari start_date trip, default jam 09:00
        start_datetime_str = f"{t['start_date']}T09:00:00"

        async with httpx.AsyncClient(timeout=120.0) as client:
            ai_response = await client.post(
                f"{ai_core_url}/api/v1/generate-itinerary",
                json={
                    "city": t["destination"],
                    "preference": t["vibe"],
                    "num_places": 5,
                    "start_datetime": start_datetime_str,
                    "duration_per_place": [60],
                    "place_type": "all",
                    "price_level": None
                }
            )

        if ai_response.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail=f"AI Core error: {ai_response.text}"
            )

        itinerary_data = ai_response.json()

        # AI Core return {"status": "success", "itinerary": [...], "weather_mode": "..."}
        itinerary_list = itinerary_data.get("itinerary", [])

        supabase.table("itinerary_items")\
            .delete()\
            .eq("trip_id", trip_id)\
            .execute()

        items_to_insert = []
        for item in itinerary_list:
            items_to_insert.append({
                "trip_id": trip_id,
                "day_number": 1,
                "order_index": item.get("step", 0),
                "place_name": item.get("name", ""),
                "place_type": item.get("type", "destination"),
                "start_time": item.get("arrival_time", ""),
                "duration_minutes": item.get("duration_spent_minutes", 60),
                "travel_time_to_next": item.get("travel_time_to_next_minutes", 0),
                "description": item.get("activity_todo", ""),
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
            "weather_mode": itinerary_data.get("weather_mode", ""),
            "itinerary": itinerary_list
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