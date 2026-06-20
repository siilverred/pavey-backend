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

async def get_wikipedia_image(query: str) -> Optional[str]:
    """
    Search Wikipedia for a given query and return its page image URL if found.
    """
    url = "https://en.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": query,
        "gsrlimit": 1,
        "prop": "pageimages",
        "piprop": "original",
        "redirects": 1
    }
    headers = {"User-Agent": "PaveyApp/1.0 (contact@pavey.app)"}
    try:
        async with httpx.AsyncClient() as client:
            # Try English Wikipedia first
            res = await client.get(url, params=params, headers=headers, timeout=5.0)
            if res.status_code == 200:
                data = res.json()
                pages = data.get("query", {}).get("pages", {})
                for page_id, page in pages.items():
                    if "original" in page:
                        return page["original"].get("source")
            
            # Try Indonesian Wikipedia
            url_id = "https://id.wikipedia.org/w/api.php"
            res = await client.get(url_id, params=params, headers=headers, timeout=5.0)
            if res.status_code == 200:
                data = res.json()
                pages = data.get("query", {}).get("pages", {})
                for page_id, page in pages.items():
                    if "original" in page:
                        return page["original"].get("source")
    except Exception as e:
        print(f"[WikipediaImage] Error searching image for {query}: {e}")
    return None

async def enrich_place_details(place_name: str, city: str) -> Dict[str, Any]:
    """
    Search place on Google Places API to fetch real photo URL, rating, and price level.
    """
    photo_url = None
    rating = None
    user_ratings = None
    latitude = None
    longitude = None
    estimated_cost = 0

    if PLACES_KEY:
        url = "https://places.googleapis.com/v1/places:searchText"
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": PLACES_KEY,
            "X-Goog-FieldMask": "places.id,places.displayName,places.photos,places.priceLevel,places.rating,places.userRatingCount,places.location"
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
                        photos = best_match.get("photos", [])
                        if photos:
                            photo_name = photos[0].get("name")
                            if photo_name:
                                photo_url = f"https://places.googleapis.com/v1/{photo_name}/media?key={PLACES_KEY}&maxWidthPx=800"
                        
                        # 2. Get Price Level and map to estimated cost in IDR
                        price_level_str = best_match.get("priceLevel")
                        if price_level_str in PRICE_MAPPING:
                            estimated_cost = PRICE_MAPPING[price_level_str]
                        elif "restaurant" in place_name.lower() or "cafe" in place_name.lower():
                            estimated_cost = 45000
                        
                        rating = best_match.get("rating")
                        user_ratings = best_match.get("userRatingCount")
                        
                        location = best_match.get("location", {})
                        latitude = location.get("latitude")
                        longitude = location.get("longitude")
                else:
                    print(f"[GooglePlaces] API returned status {res.status_code}: {res.text}")
        except Exception as e:
            print(f"[GooglePlaces] Error fetching place details for {query}: {e}")

    # Fallback to Wikipedia if Google Places photo is not available (either key not configured, API error, or no photo found)
    if not photo_url:
        print(f"[GooglePlaces] Photo not found or Google API failed for {place_name}. Trying Wikipedia fallback...")
        wiki_img = await get_wikipedia_image(place_name)
        if not wiki_img:
            wiki_img = await get_wikipedia_image(f"{place_name} {city}")
        if wiki_img:
            photo_url = wiki_img
            print(f"[GooglePlaces] Wikipedia photo found for {place_name}: {wiki_img}")

    return {
        "image": photo_url,
        "cost": estimated_cost if estimated_cost > 0 else (45000 if ("restaurant" in place_name.lower() or "cafe" in place_name.lower()) else 0),
        "rating": rating,
        "total_reviews": user_ratings,
        "latitude": latitude,
        "longitude": longitude
    }

