import sys
import os

from services.supabase_client import supabase

def inspect_db():
    tables = [
        "users",
        "user_preferences",
        "trips",
        "itinerary_items",
        "saved_places",
        "expenses"
    ]
    
    print("=== INSPECTING SUPABASE DATABASE ===")
    print("Supabase URL:", os.getenv("SUPABASE_URL"))
    
    for t in tables:
        print(f"\n--- Checking table: {t} ---")
        try:
            res = supabase.table(t).select("*").limit(5).execute()
            print(f"Success! Found {len(res.data)} record(s).")
            for i, row in enumerate(res.data):
                print(f"Record {i+1}: {row}")
        except Exception as e:
            print(f"ERROR querying table {t}: {e}")

if __name__ == "__main__":
    inspect_db()
