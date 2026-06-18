import os
import httpx
from typing import Optional, Dict, Any

PLACES_KEY = os.getenv("GOOGLE_PLACES_API_KEY")

PRICE_MAPPING = {
    "PRICE_LEVEL_FREE": 0,
    "PRICE_LEVEL_INEXPENSIVE": 35000,
    "PRICE_LEVEL_MODERATE": 100000,
    "PRICE_LEVEL_EXPENSIVE": 250000,
    "PRICE_LEVEL_VERY_EXPENSIVE": 600000
}

async def enrich_place_details(place_name: str, city: str) -> Dict[str, Any]:
    """
    Search place on Google Places API to fetch real photo URL, rating, and price level.
    """
    if not PLACES_KEY:
        print("[GooglePlaces] API key not configured.")
        return {}

    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": PLACES_KEY,
        "X-Goog-FieldMask": "places.id,places.displayName,places.photos,places.priceLevel,places.rating,places.userRatingCount"
    }

    # Query with city context to improve search accuracy
    query = f"{place_name} {city}"
    payload = {
        "textQuery": query,
        "languageCode": "id"
    }

    try:
        async with httpx.AsyncClient() as client:
            res = await client.post(url, json=payload, headers=headers, timeout=5.0)
            if res.status_code == 200:
                data = res.json()
                places = data.get("places", [])
                if places:
                    best_match = places[0]
                    
                    # 1. Get Photo URL
                    photo_url = None
                    photos = best_match.get("photos", [])
                    if photos:
                        photo_name = photos[0].get("name")
                        if photo_name:
                            # Direct media URL redirect link from Google API
                            photo_url = f"https://places.googleapis.com/v1/{photo_name}/media?key={PLACES_KEY}&maxWidthPx=800"
                    
                    # 2. Get Price Level and map to estimated cost in IDR
                    price_level_str = best_match.get("priceLevel")
                    estimated_cost = 0
                    if price_level_str in PRICE_MAPPING:
                        estimated_cost = PRICE_MAPPING[price_level_str]
                    elif "restaurant" in place_name.lower() or "cafe" in place_name.lower():
                        # Default eatery price if unspecified
                        estimated_cost = 45000
                    
                    rating = best_match.get("rating")
                    user_ratings = best_match.get("userRatingCount")
                    
                    return {
                        "image": photo_url,
                        "cost": estimated_cost,
                        "rating": rating,
                        "total_reviews": user_ratings
                    }
            else:
                print(f"[GooglePlaces] API returned status {res.status_code}: {res.text}")
    except Exception as e:
        print(f"[GooglePlaces] Error fetching place details for {query}: {e}")
        
    return {}
