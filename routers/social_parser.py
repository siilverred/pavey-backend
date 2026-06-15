from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from services.supabase_client import supabase
from services.llama_service import chat_with_llama
from middleware.auth_middleware import get_current_user
from typing import Optional
import httpx
import re
import json  # <-- INI YANG HILANG, makanya swagger tidak load router ini
from bs4 import BeautifulSoup

router = APIRouter()

class SocialParseRequest(BaseModel):
    url: str
    trip_id: Optional[str] = None

def detect_platform(url: str) -> str:
    if "instagram.com" in url:
        return "instagram"
    elif "tiktok.com" in url:
        return "tiktok"
    elif "twitter.com" in url or "x.com" in url:
        return "twitter"
    elif "youtube.com" in url or "youtu.be" in url:
        return "youtube"
    else:
        return "unknown"

async def fetch_page_content(url: str) -> str:
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)

        soup = BeautifulSoup(response.text, "html.parser")

        og_title = ""
        og_title_tag = soup.find("meta", property="og:title")
        if og_title_tag:
            og_title = og_title_tag.get("content", "")

        og_desc = ""
        og_tag = soup.find("meta", property="og:description")
        if og_tag:
            og_desc = og_tag.get("content", "")

        meta_desc = ""
        meta_tag = soup.find("meta", attrs={"name": "description"})
        if meta_tag:
            meta_desc = meta_tag.get("content", "")

        content_parts = []
        if og_title:
            content_parts.append(f"Judul: {og_title}")
        if og_desc:
            content_parts.append(f"Deskripsi: {og_desc}")
        elif meta_desc:
            content_parts.append(f"Deskripsi: {meta_desc}")

        body_text = soup.get_text(separator=" ", strip=True)
        if body_text:
            content_parts.append(f"Konten: {body_text[:2000]}")

        return "\n".join(content_parts) if content_parts else "Konten tidak bisa diambil"

    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail=f"Gagal mengambil konten dari URL: {str(e)}"
        )

@router.post("/parse")
async def parse_social_media(
    data: SocialParseRequest,
    current_user = Depends(get_current_user)
):
    result_text = ""
    try:
        platform = detect_platform(data.url)
        page_content = await fetch_page_content(data.url)

        system_prompt = """Kamu adalah AI yang bertugas mengekstrak informasi itinerary perjalanan dari konten media sosial.
Analisis konten yang diberikan dan ekstrak rekomendasi tempat wisata, restoran, atau aktivitas yang disebutkan.
Kembalikan HANYA JSON object mentah, tanpa penjelasan, tanpa markdown, tanpa code block.

Format JSON:
{
    "source_platform": "nama platform",
    "destination": "kota/negara tujuan jika disebutkan",
    "places": [
        {
            "name": "nama tempat",
            "type": "destination/restaurant/activity",
            "description": "deskripsi singkat",
            "tips": "tips atau catatan dari konten jika ada"
        }
    ],
    "raw_summary": "ringkasan singkat konten asli dalam 1-2 kalimat"
}

Jika tidak ada informasi itinerary, kembalikan:
{"error": "Tidak ada informasi itinerary yang ditemukan dalam konten ini"}"""

        user_message = f"""Platform: {platform}
URL: {data.url}

Konten halaman:
{page_content}"""

        result_text = chat_with_llama(user_message, system_prompt)
        print(f"[SocialParser Debug] Raw response: {repr(result_text)}")

        clean = result_text.strip()
        clean = re.sub(r"```json\s*", "", clean)
        clean = re.sub(r"```\s*", "", clean)
        clean = clean.strip()

        start = clean.find('{')
        end = clean.rfind('}')
        if start != -1 and end != -1 and end > start:
            clean = clean[start:end+1]

        result = json.loads(clean)

        if result.get("error"):
            raise HTTPException(status_code=422, detail=result["error"])

        if data.trip_id and result.get("places"):
            for place in result["places"]:
                try:
                    supabase.table("saved_places").insert({
                        "user_id": current_user.id,
                        "place_name": place.get("name", ""),
                        "place_type": place.get("type", "destination"),
                        "notes": place.get("tips", ""),
                        "source_url": data.url,
                        "source_platform": platform
                    }).execute()
                except Exception:
                    pass

        return {
            "platform": platform,
            "url": data.url,
            "parsed_result": result,
            "places_count": len(result.get("places", [])),
            "saved_to_trip": data.trip_id is not None
        }

    except json.JSONDecodeError as e:
        print(f"[SocialParser Debug] JSONDecodeError: {e}")
        print(f"[SocialParser Debug] Attempted to parse: {repr(result_text)}")
        raise HTTPException(
            status_code=422,
            detail="Gagal memparse konten — coba dengan URL yang berbeda"
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"[SocialParser Debug] Exception: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/supported-platforms")
async def get_supported_platforms():
    return {
        "supported": ["instagram", "tiktok", "twitter", "x", "youtube", "general_url"],
        "notes": "Instagram dan TikTok mungkin memerlukan URL publik (bukan akun private)",
        "tip": "URL dari caption postingan travel biasanya paling banyak mengandung info itinerary"
    }