from fastapi import APIRouter, HTTPException, Depends
from services.supabase_client import supabase
from middleware.auth_middleware import get_current_user
from pydantic import BaseModel
from typing import Any, Dict
import json

router = APIRouter()

class PlaceSaveRequest(BaseModel):
    place: Dict[str, Any]

@router.post("/")
async def save_place(
    data: PlaceSaveRequest,
    current_user = Depends(get_current_user)
):
    try:
        place = data.place
        place_name = place.get("name")
        if not place_name:
            raise HTTPException(status_code=400, detail="Place name is required")

        place_type = place.get("type") or place.get("place_type") or place.get("category") or "destination"

        # Delete existing same-name saved place for this user to avoid duplication
        try:
            supabase.table("saved_places")\
                .delete()\
                .eq("user_id", current_user.id)\
                .eq("place_name", place_name)\
                .execute()
        except Exception:
            pass

        res = supabase.table("saved_places").insert({
            "user_id": current_user.id,
            "place_name": place_name,
            "place_type": place_type,
            "location": json.dumps(place)
        }).execute()

        return {"message": "Place saved successfully", "data": res.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/")
async def get_saved_places(
    current_user = Depends(get_current_user)
):
    try:
        res = supabase.table("saved_places")\
            .select("*")\
            .eq("user_id", current_user.id)\
            .execute()

        places = []
        for item in res.data:
            loc_str = item.get("location")
            if loc_str:
                try:
                    place_obj = json.loads(loc_str)
                    # Use table row ID if place object does not have id
                    if "id" not in place_obj:
                        place_obj["id"] = item["id"]
                    places.append(place_obj)
                except Exception:
                    places.append({
                        "id": item["id"],
                        "name": item["place_name"],
                        "type": item["place_type"],
                    })
            else:
                places.append({
                    "id": item["id"],
                    "name": item["place_name"],
                    "type": item["place_type"],
                })
        return {"places": places}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/name/{place_name}")
async def delete_saved_place_by_name(
    place_name: str,
    current_user = Depends(get_current_user)
):
    try:
        supabase.table("saved_places")\
            .delete()\
            .eq("user_id", current_user.id)\
            .eq("place_name", place_name)\
            .execute()
        return {"message": f"Place '{place_name}' unsaved successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
