from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import WebSocket

KST = timezone(timedelta(hours=9))


class AppState:
    def __init__(self):
        self.latest_data: Optional[dict] = None
        self.heart_rate: Optional[float] = None
        self.presence_changed_at: Optional[datetime] = None
        self._last_presence: Optional[bool] = None
        self.clients: list[WebSocket] = []

    def update(self, row: dict, heart_rate: Optional[float] = None):
        presence = row.get("presence")
        if presence != self._last_presence:
            self.presence_changed_at = datetime.now(KST)
            self._last_presence = presence
        self.latest_data = row
        self.heart_rate = heart_rate

    async def broadcast(self, data: dict):
        for client in self.clients.copy():
            try:
                await client.send_json(data)
            except Exception:
                self.clients.remove(client)


state = AppState()
