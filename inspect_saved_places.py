import sys
import os

from services.supabase_client import supabase

def inspect_saved_places():
    test_user_id = 'c66c03a3-f355-4334-b140-66145eb67f8f'
    print("=== INSPECTING SAVED_PLACES COLUMNS ===")
    
    # Try inserting with potential column names to see what fails/succeeds
    potential_cols = [
        "place_name", "place_type", "notes", "source_url", "source_platform",
        "place_id", "rating", "image", "description", "lat", "lng", "category",
        "created_at", "trip_id", "user_id"
    ]
    
    # Try inserting user_id + one other col at a time
    for col in potential_cols:
        if col == "user_id":
            continue
        try:
            res = supabase.table("saved_places").insert({
                "user_id": test_user_id,
                col: "test_val" if col not in ["rating", "lat", "lng"] else 1.0
            }).execute()
            print(f"Column '{col}' EXISTS! Successfully inserted.")
            # Clean up the test insertion if possible, or just delete it
            if res.data:
                inserted_id = res.data[0]['id']
                supabase.table("saved_places").delete().eq("id", inserted_id).execute()
        except Exception as e:
            err_msg = str(e)
            if "does not exist" in err_msg or "not found" in err_msg:
                # Column doesn't exist
                pass
            else:
                # Column exists but failed validation or type constraint
                print(f"Column '{col}' EXISTS (failed with constraint): {err_msg}")

if __name__ == "__main__":
    inspect_saved_places()
