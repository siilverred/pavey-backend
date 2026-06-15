from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from services.supabase_client import supabase
import traceback

security = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    token = credentials.credentials
    try:
        user = supabase.auth.get_user(token)
        if not user or not user.user:
            raise HTTPException(status_code=401, detail="Token tidak valid atau sudah expired")
        return user.user
    except HTTPException:
        raise
    except Exception as e:
        err_str = str(e).lower()
        if "expired" in err_str or "invalid" in err_str or "jwt" in err_str:
            raise HTTPException(status_code=401, detail="Token sudah expired, silakan login ulang")
        print(f"[Auth] Error verifying token: {traceback.format_exc()}")
        raise HTTPException(status_code=401, detail="Unauthorized")