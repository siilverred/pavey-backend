from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from services.supabase_client import supabase
from middleware.auth_middleware import get_current_user
from typing import List

router = APIRouter()

class AuthRequest(BaseModel):
    email: str
    password: str

class OnboardingSave(BaseModel):
    name: str
    vibe: str
    budget: float
    destinations: List[str]

@router.post("/register")
async def register(data: AuthRequest):
    user = None

    # Strategy 1: admin.create_user — no email sent, no rate limit, auto-confirmed.
    # This works when the Supabase service role key has admin privileges.
    try:
        res = supabase.auth.admin.create_user({
            "email": data.email,
            "password": data.password,
            "email_confirm": True,
        })
        if res and res.user:
            user = res.user
    except Exception as admin_err:
        print(f"[Auth] admin.create_user failed ({admin_err}), falling back to sign_up")

    # Strategy 2: sign_up fallback — sends confirmation email (rate-limited by Supabase).
    # Used when admin creation is unavailable.
    if user is None:
        try:
            res2 = supabase.auth.sign_up({
                "email": data.email,
                "password": data.password,
            })
            if not res2 or not res2.user:
                raise HTTPException(status_code=400, detail="Registrasi gagal — coba lagi")
            user = res2.user
            # Auto-confirm so user can log in immediately without checking email
            try:
                supabase.auth.admin.update_user_by_id(user.id, {"email_confirm": True})
            except Exception as confirm_err:
                print(f"[Auth] Warning: Could not auto-confirm email: {confirm_err}")
        except HTTPException:
            raise
        except Exception as e:
            err_msg = str(e)
            if "rate limit" in err_msg.lower() or "429" in err_msg:
                raise HTTPException(
                    status_code=429,
                    detail="Terlalu banyak percobaan registrasi. Coba lagi dalam beberapa menit."
                )
            raise HTTPException(status_code=400, detail=err_msg)

    # Sync user record to 'users' table
    try:
        supabase.table("users").upsert({
            "id": user.id,
            "email": user.email,
            "name": user.email.split("@")[0],
        }).execute()
    except Exception as e:
        print(f"[Auth] Failed to insert to users table: {e}")

    return {"message": "Register berhasil", "user_id": user.id}


@router.post("/login")
async def login(data: AuthRequest):
    try:
        res = supabase.auth.sign_in_with_password({
            "email": data.email,
            "password": data.password
        })
        if res and res.user:
            try:
                # Pastikan data user ada di tabel 'users' (sync)
                supabase.table("users").upsert({
                    "id": res.user.id,
                    "email": res.user.email,
                    "name": res.user.user_metadata.get("full_name") or res.user.email.split("@")[0]
                }).execute()
            except Exception as e:
                print(f"[Auth] Failed to sync login to users table: {e}")
        return {
            "access_token": res.session.access_token,
            "user_id": res.user.id,
            "email": res.user.email
        }
    except Exception as e:
        raise HTTPException(status_code=401, detail="Email atau password salah")

@router.post("/logout")
async def logout():
    try:
        supabase.auth.sign_out()
        return {"message": "Logout berhasil"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/onboarding")
async def save_onboarding(
    data: OnboardingSave,
    current_user = Depends(get_current_user)
):
    try:
        # 1. Update nama user di tabel 'users'
        supabase.table("users").upsert({
            "id": current_user.id,
            "email": current_user.email,
            "name": data.name
        }).execute()

        # 2. Update user_metadata full_name di Supabase Auth
        try:
            supabase.auth.update_user({
                "data": {"full_name": data.name}
            })
        except Exception as e:
            print(f"[Auth] Failed to update user metadata: {e}")

        # 3. Simpan preferences ke tabel 'user_preferences', menjaga chat history jika ada
        vibe_history = {"vibes": [data.vibe], "chats": {}}
        try:
            res_pref = supabase.table("user_preferences").select("vibe_history").eq("user_id", current_user.id).execute()
            if res_pref.data and res_pref.data[0].get("vibe_history"):
                existing_vh = res_pref.data[0]["vibe_history"]
                if isinstance(existing_vh, dict):
                    if "chats" in existing_vh or "vibes" in existing_vh:
                        vibe_history["chats"] = existing_vh.get("chats") or {}
                        existing_vibes = existing_vh.get("vibes") or []
                        if isinstance(existing_vibes, list):
                            vibe_history["vibes"] = list(set(existing_vibes + [data.vibe]))
                        else:
                            vibe_history["vibes"] = [data.vibe]
                    else:
                        vibe_history["chats"] = existing_vh
                        vibe_history["vibes"] = [data.vibe]
                elif isinstance(existing_vh, list):
                    vibe_history["vibes"] = list(set(existing_vh + [data.vibe]))
        except Exception as e:
            print(f"[Auth] Failed to load/parse existing user_preferences: {e}")

        supabase.table("user_preferences").upsert({
            "user_id": current_user.id,
            "vibe_history": vibe_history,
            "budget_min": int(data.budget),
            "budget_max": int(data.budget),
            "destination_type": "mixed",
            "updated_at": "now()"
        }, on_conflict="user_id").execute()

        return {"message": "Onboarding berhasil disimpan ke database"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/me")
async def get_me(current_user = Depends(get_current_user)):
    name = current_user.email.split("@")[0]
    try:
        # Coba ambil nama dari tabel 'users'
        res = supabase.table("users").select("name").eq("id", current_user.id).single().execute()
        if res.data and res.data.get("name"):
            name = res.data["name"]
    except Exception:
        # Fallback ke user_metadata
        if current_user.user_metadata and current_user.user_metadata.get("full_name"):
            name = current_user.user_metadata["full_name"]
    return {
        "user_id": current_user.id,
        "email": current_user.email,
        "name": name
    }