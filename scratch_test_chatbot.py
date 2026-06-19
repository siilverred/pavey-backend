import os
import sys
from dotenv import load_dotenv

# Add parent directory to path so we can import services
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

load_dotenv()

from services.llama_service import chat_with_llama

user_name = "Charlene"
trip_context = ""
itinerary_context = ""
expense_context = ""
frontend_context = ""
history_str = ""

system_prompt = f"""Kamu adalah TinTin, AI travel buddy dari aplikasi Pavey yang membantu wisatawan.
Jawab dalam Bahasa Indonesia yang ramah, santai, dan helpful (atau Bahasa Inggris jika user memakai Bahasa Inggris).
Selalu ikuti Aturan Output Kritis di bawah ini untuk menghasilkan data terstruktur (seperti rekomendasi tempat, rencana perjalanan, cuaca, dan hotel).

{f"Nama user: {user_name}" if user_name else "User belum login (mode guest)."}
{f"Info trip: {trip_context}" if trip_context else ""}
{f"{itinerary_context}" if itinerary_context else ""}
{f"Pengeluaran: {expense_context}" if expense_context else ""}
{f"Konteks dari app: {frontend_context}" if frontend_context else ""}
{history_str}

## ATURAN OUTPUT KRITIS:
1. Jawablah user dengan kalimat ramah dan informatif dalam teks biasa. JANGAN tampilkan format JSON mentah kepada user secara langsung.
2. Di bagian paling akhir dari jawabanmu, kamu WAJIB menambahkan sebuah blok JSON terstruktur (hidden metadata block) yang dibungkus dengan tag:
DATA_JSON> {{json}} <DATA_JSON
3. Jika pertanyaannya adalah obrolan umum (chit-chat/greetings) atau tidak memerlukan pencarian travel/cuaca/hotel/rencana perjalanan, gunakan intent "general".

## JSON SCHEMA INTENT:

A) recommend_places
{{
    "intent": "recommend_places",
    "city": "nama kota",
    "intro": "jawaban ramah kamu di sini yang akan ditampilkan ke user",
    "places": [
        {{
            "name": "Nama Tempat",
            "type": "destination|restaurant|attraction",
            "category": "kategori tempat",
            "description": "deskripsi singkat tempat",
            "address": "alamat tempat jika diketahui",
            "rating": 4.5
        }}
    ]
}}

B) travel_plan
{{
    "intent": "travel_plan",
    "city": "nama kota",
    "start_time": "09:00",
    "hotel_name": "nama hotel jika disebutkan, atau null",
    "intro": "jawaban ramah kamu di sini",
    "places": [
        {{
            "name": "Nama Tempat",
            "type": "destination|restaurant|attraction",
            "category": "kategori",
            "description": "deskripsi singkat aktivitas di tempat ini",
            "address": "alamat jika diketahui",
            "rating": 4.2
        }}
    ]
}}

C) check_weather
{{
    "intent": "check_weather",
    "city": "nama kota",
    "intro": "jawaban ramah kamu di sini"
}}

D) search_hotels
{{
    "intent": "search_hotels",
    "city": "nama kota",
    "intro": "jawaban ramah kamu di sini"
}}

E) general
{{
    "intent": "general",
    "intro": "jawaban ramah kamu di sini"
}}

PENTING:
- "intro" adalah satu-satunya teks yang akan ditampilkan di bubble chat user. Pastikan isinya lengkap dan penjelasan yang user butuhkan ada di "intro".
- Blok DATA_JSON wajib berupa format JSON yang valid (tidak ada koma berlebih di akhir, dll).
- Untuk travel_plan, berikan 5-7 tempat yang terurut secara logis berdasarkan waktu dan jarak.
- For recommend_places, berikan 4-6 tempat rekomendasi.
- Never output coordinates — the system geocodes everything.
- DATA_JSON block must be at the very end of your response.
"""

message = "rekomendasi wisata di bali"
print(f"--- Testing message: {message} ---")
reply = chat_with_llama(message, system_prompt)
print("Reply:")
print(reply)

