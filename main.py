from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.security import HTTPBearer
from routers import auth, trips, weather, wallet, chatbot, receipt, social_parser
from scheduler.morning_briefing import start_scheduler

security = HTTPBearer()

@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield

app = FastAPI(title="Pavey API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(trips.router, prefix="/trips", tags=["Trips"])
app.include_router(weather.router, prefix="/weather", tags=["Weather"])
app.include_router(wallet.router, prefix="/wallet", tags=["Wallet"])
app.include_router(chatbot.router, prefix="/chatbot", tags=["Chatbot"])
app.include_router(receipt.router, prefix="/receipt", tags=["Receipt"])
app.include_router(social_parser.router, prefix="/social", tags=["Social Parser"])

@app.get("/")
def root():
    return {"status": "Pavey API is running", "version": "1.0.0"}

@app.get("/health")
def health_check():
    """Cek status semua service — tidak perlu auth."""
    import os
    checks = {
        "supabase_url": bool(os.getenv("SUPABASE_URL")),
        "supabase_key": bool(os.getenv("SUPABASE_SERVICE_KEY")),
        "groq_api_key": bool(os.getenv("GROQ_API_KEY")),
        "openrouter_key": bool(os.getenv("OPENROUTER_API_KEY")),
        "openweather_key": bool(os.getenv("OPENWEATHER_API_KEY")),
        "gemini_key": bool(os.getenv("GEMINI_API_KEY")),
    }
    all_ok = all(checks.values())
    return {
        "status": "healthy" if all_ok else "degraded",
        "env_checks": checks,
        "missing_keys": [k for k, v in checks.items() if not v]
    }

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title="Pavey API",
        version="1.0.0",
        routes=app.routes,
    )
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
        }
    }
    for path in openapi_schema["paths"].values():
        for method in path.values():
            method["security"] = [{"BearerAuth": []}]
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi_schema = None
app.openapi = custom_openapi