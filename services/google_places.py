import os
import httpx
import hashlib
from typing import Optional, Dict, Any

PLACES_KEY = os.getenv("GOOGLE_PLACES_API_KEY")

CITY_IMAGE_CACHE = {}

async def get_cached_city_image(city: str) -> Optional[str]:
    """
    Fetch and cache a real photo of the city from Wikidata/Wikipedia.
    """
    if not city:
        return None
    city_clean = city.strip().split(',')[0].strip()
    if city_clean in CITY_IMAGE_CACHE:
        return CITY_IMAGE_CACHE[city_clean]
    
    # Try Wikidata search first
    img = await get_wikidata_image(city_clean)
    if not img:
        # Try Wikipedia search
        img = await get_wikipedia_image(city_clean)
        
    if img:
        CITY_IMAGE_CACHE[city_clean] = img
    return img

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
                    title = page.get("title", "")
                    title_lower = title.lower()
                    query_lower = query.lower()
                    generic_titles = {
                        "bali", "lombok", "jakarta", "bandung", "yogyakarta", "indonesia", 
                        "surabaya", "medan", "semarang", "makassar", "denpasar", "singapore",
                        "malaysia", "kuala lumpur", "thailand", "bangkok", "phuket"
                    }
                    if title_lower in generic_titles and title_lower != query_lower:
                        continue
                    
                    # Relevance check to avoid completely wrong matches
                    q_clean = query_lower.replace("indonesia", "").strip()
                    t_clean = title_lower.replace("indonesia", "").strip()
                    q_words = set(w for w in q_clean.split() if len(w) > 2)
                    t_words = set(w for w in t_clean.split() if len(w) > 2)
                    is_match = False
                    if q_clean in t_clean or t_clean in q_clean:
                        is_match = True
                    elif q_words and t_words and q_words.intersection(t_words):
                        # Subtract generic words to avoid wrong matches on terms like 'cafe', 'restaurant'
                        overlap = q_words.intersection(t_words)
                        if overlap - {"cafe", "restaurant", "studio", "hotel", "coffee", "shop", "bar", "place", "street"}:
                            is_match = True
                    
                    if not is_match:
                        continue

                    if "original" in page:
                        return page["original"].get("source")
            
            # Try Indonesian Wikipedia
            url_id = "https://id.wikipedia.org/w/api.php"
            res = await client.get(url_id, params=params, headers=headers, timeout=5.0)
            if res.status_code == 200:
                data = res.json()
                pages = data.get("query", {}).get("pages", {})
                for page_id, page in pages.items():
                    title = page.get("title", "")
                    title_lower = title.lower()
                    query_lower = query.lower()
                    generic_titles = {
                        "bali", "lombok", "jakarta", "bandung", "yogyakarta", "indonesia", 
                        "surabaya", "medan", "semarang", "makassar", "denpasar", "singapore",
                        "malaysia", "kuala lumpur", "thailand", "bangkok", "phuket"
                    }
                    if title_lower in generic_titles and title_lower != query_lower:
                        continue

                    # Relevance check to avoid completely wrong matches
                    q_clean = query_lower.replace("indonesia", "").strip()
                    t_clean = title_lower.replace("indonesia", "").strip()
                    q_words = set(w for w in q_clean.split() if len(w) > 2)
                    t_words = set(w for w in t_clean.split() if len(w) > 2)
                    is_match = False
                    if q_clean in t_clean or t_clean in q_clean:
                        is_match = True
                    elif q_words and t_words and q_words.intersection(t_words):
                        overlap = q_words.intersection(t_words)
                        if overlap - {"cafe", "restaurant", "studio", "hotel", "coffee", "shop", "bar", "place", "street"}:
                            is_match = True
                    
                    if not is_match:
                        continue

                    if "original" in page:
                        return page["original"].get("source")
    except Exception as e:
        print(f"[WikipediaImage] Error searching image for {query}: {e}")
    return None

async def get_wikidata_image(query: str) -> Optional[str]:
    """
    Search Wikidata for a given query and extract the P18 image claim if available.
    Keyless, free tier, highly accurate fallback for landmarks, places and restaurant types.
    """
    search_url = "https://www.wikidata.org/w/api.php"
    search_params = {
        "action": "wbsearchentities",
        "search": query,
        "language": "id",
        "format": "json",
        "limit": 3
    }
    headers = {"User-Agent": "PaveyApp/1.0 (contact@pavey.app)"}
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(search_url, params=search_params, headers=headers, timeout=5.0)
            if res.status_code == 200:
                data = res.json()
                search_results = data.get("search", [])
                for match in search_results:
                    title = match.get("label", "")
                    title_lower = title.lower()
                    query_lower = query.lower()
                    generic_titles = {
                        "bali", "lombok", "jakarta", "bandung", "yogyakarta", "indonesia", 
                        "surabaya", "medan", "semarang", "makassar", "denpasar", "singapore",
                        "malaysia", "kuala lumpur", "thailand", "bangkok", "phuket"
                    }
                    if title_lower in generic_titles and title_lower != query_lower:
                        continue

                    # Relevance check to avoid completely wrong matches
                    q_clean = query_lower.replace("indonesia", "").strip()
                    t_clean = title_lower.replace("indonesia", "").strip()
                    q_words = set(w for w in q_clean.split() if len(w) > 2)
                    t_words = set(w for w in t_clean.split() if len(w) > 2)
                    is_match = False
                    if q_clean in t_clean or t_clean in q_clean:
                        is_match = True
                    elif q_words and t_words and q_words.intersection(t_words):
                        overlap = q_words.intersection(t_words)
                        if overlap - {"cafe", "restaurant", "studio", "hotel", "coffee", "shop", "bar", "place", "street"}:
                            is_match = True
                    
                    if not is_match:
                        continue

                    entity_id = match.get("id")
                    if not entity_id:
                        continue
                    
                    # Fetch entity data to check claims
                    entity_url = f"https://www.wikidata.org/wiki/Special:EntityData/{entity_id}.json"
                    entity_res = await client.get(entity_url, headers=headers, timeout=5.0)
                    if entity_res.status_code == 200:
                        entity_data = entity_res.json()
                        claims = entity_data.get("entities", {}).get(entity_id, {}).get("claims", {})
                        
                        # P18 is the property code for 'image' in Wikidata
                        image_claims = claims.get("P18", [])
                        if image_claims:
                            img_filename = image_claims[0].get("mainsnak", {}).get("datavalue", {}).get("value")
                            if img_filename:
                                # Clean filename (spaces to underscores)
                                name_clean = img_filename.replace(" ", "_")
                                md5 = hashlib.md5(name_clean.encode('utf-8')).hexdigest()
                                a = md5[0]
                                ab = md5[0:2]
                                return f"https://upload.wikimedia.org/wikipedia/commons/{a}/{ab}/{name_clean}"
    except Exception as e:
        print(f"[WikidataImage] Error fetching image for {query}: {e}")
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

    # Fallback to Wikidata and Wikipedia if Google Places photo is not available (key not configured, quota exhausted, or no photo found)
    if not photo_url:
        print(f"[GooglePlaces] Photo not found or Google API failed/quota-exhausted for {place_name}. Trying free-tier Wikidata/Wikipedia fallback...")
        
        # 1. Try Wikidata with place name
        wiki_img = await get_wikidata_image(place_name)
        if not wiki_img:
            # 2. Try Wikidata with place name + city context
            wiki_img = await get_wikidata_image(f"{place_name} {city}")
        
        if not wiki_img:
            # 3. Try Wikipedia with place name
            wiki_img = await get_wikipedia_image(place_name)
        
        if not wiki_img:
            # 4. Try Wikipedia with place name + city context
            wiki_img = await get_wikipedia_image(f"{place_name} {city}")
            
        # 5. Try City fallback if no specific place image was found
        if not wiki_img and city:
            wiki_img = await get_cached_city_image(city)
            
        if wiki_img:
            photo_url = wiki_img
            print(f"[GooglePlaces] Free-tier photo found for {place_name}: {wiki_img}")

    return {
        "image": photo_url,
        "cost": estimated_cost if estimated_cost > 0 else (45000 if ("restaurant" in place_name.lower() or "cafe" in place_name.lower()) else 0),
        "rating": rating,
        "total_reviews": user_ratings,
        "latitude": latitude,
        "longitude": longitude
    }

