from supabase import create_client
import os
from dotenv import load_dotenv

load_dotenv()

supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_SERVICE_KEY")

if not supabase_url or not supabase_key:
    print("[SupabaseClient] Warning: SUPABASE_URL or SUPABASE_SERVICE_KEY is missing. Supabase client is initialized as None.")
    supabase = None
else:
    try:
        supabase = create_client(supabase_url, supabase_key)
    except Exception as e:
        print(f"[SupabaseClient] Error initializing Supabase client: {e}")
        supabase = None