from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.supabase_client import supabase

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