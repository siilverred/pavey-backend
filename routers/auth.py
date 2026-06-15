from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from services.supabase_client import supabase
from middleware.auth_middleware import get_current_user

router = APIRouter()

class AuthRequest(BaseModel):
    email: str
    password: str

@router.post("/register")
async def register(data: AuthRequest):
    try:
        res = supabase.auth.sign_up({
            "email": data.email,
            "password": data.password
        })
        return {"message": "Register berhasil", "user_id": res.user.id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/login")
async def login(data: AuthRequest):
    try:
        res = supabase.auth.sign_in_with_password({
            "email": data.email,
            "password": data.password
        })
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

@router.get("/me")
async def get_me(current_user = Depends(get_current_user)):
    return {
        "user_id": current_user.id,
        "email": current_user.email,
        "name": current_user.user_metadata.get("full_name", current_user.email.split("@")[0])
    }