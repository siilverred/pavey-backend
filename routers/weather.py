from fastapi import APIRouter, HTTPException
from services.weather_service import get_current_weather, get_forecast

router = APIRouter()

@router.get("/current")
async def current_weather(lat: float, lon: float):
    try:
        return await get_current_weather(lat, lon)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/forecast")
async def weather_forecast(lat: float, lon: float):
    try:
        return await get_forecast(lat, lon)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))