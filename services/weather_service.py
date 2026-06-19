import httpx
import os
from dotenv import load_dotenv

load_dotenv()

WEATHER_KEY = os.getenv("OPENWEATHER_API_KEY")

async def get_current_weather(lat: float, lon: float):
    async with httpx.AsyncClient() as client:
        res = await client.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={
                "lat": lat,
                "lon": lon,
                "appid": WEATHER_KEY,
                "units": "metric",
                "lang": "id"
            }
        )
    data = res.json()
    return {
        "city": data.get("name", "Unknown City"),
        "temp_celsius": data["main"]["temp"],
        "feels_like": data["main"]["feels_like"],
        "humidity": data["main"]["humidity"],
        "wind_speed": data["wind"]["speed"] * 3.6 if "wind" in data else 0.0,
        "condition": data["weather"][0]["description"],
        "icon": data["weather"][0]["icon"],
        "rain": data.get("rain", {}).get("1h", 0.0)
    }

async def get_forecast(lat: float, lon: float):
    async with httpx.AsyncClient() as client:
        res = await client.get(
            "https://api.openweathermap.org/data/2.5/forecast",
            params={
                "lat": lat,
                "lon": lon,
                "appid": WEATHER_KEY,
                "units": "metric",
                "lang": "id",
                "cnt": 5
            }
        )
    data = res.json()
    forecasts = []
    for item in data["list"]:
        forecasts.append({
            "time": item["dt_txt"],
            "temp_celsius": item["main"]["temp"],
            "condition": item["weather"][0]["description"],
            "icon": item["weather"][0]["icon"]
        })
    return forecasts