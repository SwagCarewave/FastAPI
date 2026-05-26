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
        self.hardware_connected: bool = False
        self.clients: list[WebSocket] = []
        self.breathing_clients: list[WebSocket] = []
        self.presence_clients: list[WebSocket] = []

    def update(self, row: dict, heart_rate: Optional[float] = None):
        presence = row.get("presence")
        if presence != self._last_presence:
            self.presence_changed_at = datetime.now(KST)
            self._last_presence = presence
        self.latest_data = row
        self.heart_rate = heart_rate

    async def _send_all(self, clients: list[WebSocket], data: dict):
        for client in clients.copy():
            try:
                await client.send_json(data)
            except Exception:
                clients.remove(client)

    async def broadcast(self, data: dict):
        await self._send_all(self.clients, data)

    async def broadcast_breathing(self, data: dict):
        await self._send_all(self.breathing_clients, data)

    async def broadcast_presence(self, data: dict):
        await self._send_all(self.presence_clients, data)


state = AppState()
