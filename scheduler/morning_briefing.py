from apscheduler.schedulers.asyncio import AsyncIOScheduler
from services.supabase_client import supabase
from datetime import date

scheduler = AsyncIOScheduler()

async def poll_weather_for_active_trips():
    try:
        today = str(date.today())
        res = supabase.table("trips")\
            .select("*")\
            .lte("start_date", today)\
            .gte("end_date", today)\
            .execute()

        for trip in res.data:
            print(f"[Morning Briefing] Polling cuaca untuk: {trip['destination']}")

    except Exception as e:
        print(f"[Morning Briefing] Error: {e}")

def start_scheduler():
    scheduler.add_job(
        poll_weather_for_active_trips,
        "interval",
        minutes=30,
        id="morning_briefing"
    )
    scheduler.start()
    print("[Scheduler] Morning Briefing aktif")