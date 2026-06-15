from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from services.supabase_client import supabase
from middleware.auth_middleware import get_current_user

router = APIRouter()

class ExpenseCreate(BaseModel):
    trip_id: str
    amount: int
    category: str
    description: str

@router.post("/expenses")
async def add_expense(
    data: ExpenseCreate,
    current_user = Depends(get_current_user)
):
    try:
        res = supabase.table("expenses").insert({
            "user_id": current_user.id,
            "trip_id": data.trip_id,
            "amount": data.amount,
            "category": data.category,
            "description": data.description
        }).execute()

        return {"message": "Expense berhasil ditambahkan", "data": res.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/expenses/{trip_id}")
async def get_expenses(
    trip_id: str,
    current_user = Depends(get_current_user)
):
    try:
        res = supabase.table("expenses")\
            .select("*")\
            .eq("trip_id", trip_id)\
            .eq("user_id", current_user.id)\
            .order("created_at", desc=True)\
            .execute()

        total = sum(item["amount"] for item in res.data)

        return {
            "trip_id": trip_id,
            "total_spent_idr": total,
            "transactions": res.data
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))