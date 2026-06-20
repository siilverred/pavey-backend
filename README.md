---
title: Pavey Backend
emoji: 🐳
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# Pavey Backend Service (`backend`)

Service FastAPI sebagai gerbang utama orkestrasi data aplikasi Pavey. Menghubungkan client frontend ke Supabase PostgreSQL, scheduler untuk morning briefing, dan melayani endpoint perjalanan (trip & itinerary).

## Fitur Utama

1. **Google Places Data Enrichment**: 
   * Integrasi dengan Google Places API searchText endpoint.
   * Mengambil gambar lokasi asli (photo media redirect URL), koordinat spasial (latitude/longitude), dan informasi rating secara dinamis.
   * Memetakan tingkat harga (`priceLevel`) dari Places API secara otomatis ke Rupiah (IDR) guna meniadakan default Rp 0.
   * Dijalankan secara konkuren menggunakan `asyncio.gather` untuk performa latensi optimal.
   
2. **Duplicate-Free Multi-day Generation**:
   * Melacak daftar tempat yang sudah dihasilkan di setiap hari generasi.
   * Meneruskan parameter `exclude_names` ke AI Core di setiap loop harian agar tempat wisata pada hari berikutnya dijamin unik (tidak ada duplikasi tempat di hari lain).

3. **Secure Chatbot (TinTin)**:
   * Chatbot dengan proteksi privasi sistem.
   * Instruksi prompt secara ketat memblokir pertanyaan sensitif mengenai API eksternal yang dipakai (Google Places, OpenWeather), model LLM, arsitektur database, hosting, atau detail pengembang internal.

4. **Receipt OCR & Social Parser**:
   * Parsing data transaksi otomatis dari struk menggunakan PaddleOCR.
   * Parsing rencana perjalanan dari media sosial menggunakan integrasi Gemini LLM.

## Endpoint Utama

* `POST /trips/generate-plan`: Menghasilkan preview rencana perjalanan bagi pengguna Guest (tanpa harus login).
* `POST /trips/{trip_id}/generate`: Menghasilkan rencana perjalanan untuk trip tersimpan, memperkaya detail dengan Google Places API, dan menyimpannya ke Supabase.
* `POST /chatbot/message`: Menerima pesan chat untuk TinTin travel buddy, melacak konteks trip/itinerary, serta mengembalikan respon teks ramah beserta tag metadata JSON.
* `POST /receipt/upload`: Ekstraksi teks struk belanja dan parsing otomatis ke data transaksi.
* `POST /social/parse`: Ekstraksi detail itinerary perjalanan dari input link media sosial / teks promosi.

## Cara Penggunaan (Quick Start)

### 1. Prasyarat & Instalasi
Pastikan Anda memiliki Python 3.10+ terinstal.

1. Masuk ke direktori `backend`:
   ```bash
   cd backend
   ```
2. Buat dan aktifkan virtual environment:
   ```bash
   python -m venv venv
   # Di Windows (PowerShell):
   .\venv\Scripts\Activate
   # Di macOS/Linux:
   source venv/bin/activate
   ```
3. Instal dependensi:
   ```bash
   pip install -r requirements.txt
   ```

### 2. Konfigurasi Environment Variables
Buat file `.env` di dalam folder `backend/` dan lengkapi konfigurasi berikut:
```env
SUPABASE_URL=your_supabase_project_url
SUPABASE_SERVICE_KEY=your_supabase_service_role_key
JWT_SECRET=your_jwt_signing_secret
GEMINI_API_KEY=your_gemini_api_key
OPENWEATHER_API_KEY=your_openweathermap_api_key
GOOGLE_PLACES_API_KEY=your_google_places_api_key
GROQ_API_KEY=your_groq_api_key
OPENROUTER_API_KEY=your_openrouter_api_key
EXCHANGE_RATE_API_KEY=your_exchangerate_api_key
AI_CORE_URL=http://localhost:8000
```

### 3. Menjalankan Aplikasi
Jalankan server pengembangan FastAPI menggunakan Uvicorn:
```bash
uvicorn main:app --reload --port 8000
```
Akses dokumentasi API interaktif (Swagger UI) di `http://localhost:8000/docs`.