import asyncio
import httpx
from app.ruview.state import state

RUVIEW_STATUS_URL = "http://localhost:3000/api/v1/status"
POLL_INTERVAL = 10


async def status_checker():
    async with httpx.AsyncClient() as client:
        while True:
            try:
                resp = await client.get(RUVIEW_STATUS_URL, timeout=5.0)
                source = resp.json().get("source", "simulate")
                state.hardware_connected = source != "simulate"
            except Exception:
                state.hardware_connected = False
            await asyncio.sleep(POLL_INTERVAL)
