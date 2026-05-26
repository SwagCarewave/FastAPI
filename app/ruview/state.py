from collections import deque
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import WebSocket

KST = timezone(timedelta(hours=9))

EMA_ALPHA = 0.05        # 낮을수록 더 smooth
PRESENCE_WINDOW = 30    # 최근 30프레임
PRESENCE_THRESHOLD = 0.7  # 70% 이상이 true여야 재실


class AppState:
    def __init__(self):
        self.latest_data: Optional[dict] = None
        self.heart_rate: Optional[float] = None
        self.presence_changed_at: Optional[datetime] = None
        self.detected_at: Optional[str] = None
        self.smoothed_freq: float = 0.0
        self.stable_presence: bool = False
        self.hardware_connected: bool = False

        self._last_presence: Optional[bool] = None
        self._freq_ema: Optional[float] = None
        self._presence_buffer: deque = deque(maxlen=PRESENCE_WINDOW)

        self.clients: list[WebSocket] = []
        self.breathing_clients: list[WebSocket] = []
        self.presence_clients: list[WebSocket] = []

    def update(self, row: dict, heart_rate: Optional[float] = None):
        # EMA 스무딩
        raw_freq = row.get("dominant_freq_hz", 0)
        if self._freq_ema is None:
            self._freq_ema = raw_freq
        else:
            self._freq_ema = EMA_ALPHA * raw_freq + (1 - EMA_ALPHA) * self._freq_ema
        self.smoothed_freq = self._freq_ema

        # presence debounce (70% 임계값)
        self._presence_buffer.append(bool(row.get("presence", False)))
        ratio = sum(self._presence_buffer) / len(self._presence_buffer)
        stable = ratio > PRESENCE_THRESHOLD
        if stable != self._last_presence:
            self.presence_changed_at = datetime.now(KST)
            self._last_presence = stable
        self.stable_presence = stable

        # detected_at = 가장 최근 데이터 수신 시각 (항상 현재 시간으로 갱신)
        self.detected_at = row["timestamp"]

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
