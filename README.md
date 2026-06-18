---
title: Pavey Backend
emoji: 🐳
colorFrom: blue
colorTo: indigo
sdk: docker
pinned: false
---

# Pavey Backend Service (`backend`)

Service FastAPI sebagai gerbang utama orkestrasi data aplikasi Pavey. Menghubungkan client frontend ke Supabase PostgreSQL, scheduler untuk morning briefing, dan melayani endpoint perjalanan (trip & itinerary).

## Fitur Utama

1. **Google Places Data Enrichment**: 
   * Integrasi dengan Google Places API searchText endpoint.
   * Mengambil gambar lokasi asli (photo media redirect URL) dan informasi rating secara dinamis.
   * Memetakan tingkat harga (`priceLevel`) dari Places API secara otomatis ke Rupiah (IDR) guna meniadakan default Rp 0.
   * Dijalankan secara konkuren menggunakan `asyncio.gather` untuk performa latensi optimal.
   
2. **Duplicate-Free Multi-day Generation**:
   * Melacak daftar tempat yang sudah dihasilkan di setiap hari generasi.
   * Meneruskan parameter `exclude_names` ke AI Core di setiap loop harian agar tempat wisata pada hari berikutnya dijamin unik (tidak ada duplikasi tempat di hari lain).

3. **Secure Chatbot (TinTin)**:
   * Chatbot dengan proteksi privasi sistem.
   * Instruksi prompt secara ketat memblokir pertanyaan sensitif mengenai API eksternal yang dipakai (Google Places, OpenWeather), model LLM, arsitektur database, hosting, atau detail pengembang internal.

## Endpoint Utama

* `POST /trips/generate-plan`: Menghasilkan preview rencana perjalanan bagi pengguna Guest (tanpa harus login).
* `POST /trips/{trip_id}/generate`: Menghasilkan rencana perjalanan untuk trip tersimpan, memperkaya detail dengan Google Places API, dan menyimpannya ke Supabase.
* `POST /chatbot/message`: Menerima pesan chat untuk TinTin travel buddy, melacak konteks trip/itinerary, serta mengembalikan respon teks ramah beserta tag metadata JSON.