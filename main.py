from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.security import HTTPBearer
from routers import auth, trips, weather, wallet, chatbot, receipt
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

@app.get("/")
def root():
    return {"status": "Pavey API is running"}

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