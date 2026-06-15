import os
import httpx
from typing import Optional

async def get_rate_from_idr(target_currency: str) -> Optional[float]:
    """
    Fetch exchange rate from IDR to target_currency using ExchangeRate-API (exchangerate-api.com).
    Uses the EXCHANGE_RATE_API_KEY environment variable.
    Returns None if the key is not set, or the API call fails.
    """
    api_key = os.getenv("EXCHANGE_RATE_API_KEY")
    if not api_key:
        print("[ExchangeService] EXCHANGE_RATE_API_KEY is not set. Falling back to LLM/fallback rates.")
        return None

    # ExchangeRate-API endpoint
    url = f"https://v6.exchangerate-api.com/v6/{api_key}/pair/IDR/{target_currency.upper()}"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("result") == "success":
                    rate = float(data.get("conversion_rate"))
                    print(f"[ExchangeService] Live rate for IDR to {target_currency}: {rate}")
                    return rate
                else:
                    print(f"[ExchangeService] API error: {data.get('error-type')}")
            else:
                print(f"[ExchangeService] API returned non-200 status: {resp.status_code}")
    except Exception as e:
        print(f"[ExchangeService] Request failed: {e}")
    
    return None
