import os
import sys
from dotenv import load_dotenv

# Add parent directory to path so we can import services
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

load_dotenv()

from routers.trips import generate_fallback_itinerary

city = "Medan"
vibe = "cultural"
days = 1

print(f"Testing fallback itinerary generation for city={city}, vibe={vibe}, days={days}...")
result = generate_fallback_itinerary(city, vibe, days)
print("\nResult:")
for item in result:
    print(f"- {item.get('name')} ({item.get('type')}) - {item.get('arrival_time')}: {item.get('activity_todo')} [lat={item.get('latitude')}, lon={item.get('longitude')}]")
