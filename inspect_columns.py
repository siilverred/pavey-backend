import sys
import os

from services.supabase_client import supabase

def inspect_schema():
    print("=== INSPECTING TABLE SCHEMAS ===")
    
    # Query PostgreSQL system catalog to find columns for our tables
    tables = ["users", "user_preferences", "trips", "itinerary_items", "saved_places", "expenses"]
    
    for table in tables:
        print(f"\nColumns for table: {table}")
        try:
            # We can run an empty select or fetch a non-existent ID to get headers, 
            # but using select with limit 0 is even better to get column info from the response
            res = supabase.table(table).select("*").limit(1).execute()
            if res.data:
                print("Columns found in record:", list(res.data[0].keys()))
            else:
                # If table is empty, we can try to select a dummy column or just try to insert a dummy to see schema from error,
                # or select a specific known query. Let's try to query the REST schema if possible, or print the response keys.
                print("Table is empty. To find its columns, let's look at a trial insert or inspect the REST API definition.")
                # We can perform a dummy insert with an empty dict to trigger database error showing allowed columns
                try:
                    supabase.table(table).insert({}).execute()
                except Exception as db_err:
                    print("Allowed columns/Error detail:", str(db_err))
        except Exception as e:
            print(f"Error inspecting {table}: {e}")

if __name__ == "__main__":
    inspect_schema()
