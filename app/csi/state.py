from collections import deque
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import WebSocket

KST = timezone(timedelta(hours=9))

EMA_ALPHA = 0.05
PRESENCE_WINDOW = 30
PRESENCE_THRESHOLD = 0.7

# 실제 호흡 주파수 범위 (Hz) — 이 범위 밖은 노이즈로 간주
BREATHING_FREQ_MIN = 0.1   # 6 bpm
BREATHING_FREQ_MAX = 0.6   # 36 bpm


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
        self._fall_locked_until: Optional[datetime] = None
        self.last_fall_event_at: Optional[datetime] = None

        self.last_fall_data: Optional[dict] = None

        self.clients: list[WebSocket] = []
        self.breathing_clients: list[WebSocket] = []
        self.presence_clients: list[WebSocket] = []
        self.fall_clients: list[WebSocket] = []

    def set_fall_lock(self, duration_sec: int = 30):
        self._fall_locked_until = datetime.now(KST) + timedelta(seconds=duration_sec)

    def _is_fall_locked(self) -> bool:
        if self._fall_locked_until is None:
            return False
        return datetime.now(KST) < self._fall_locked_until

    def update_from_csi(self, is_present: bool, timestamp: str):
        # 낙상 이벤트 이후 일정 시간은 재실 강제 유지
        if self._is_fall_locked():
            is_present = True

        self._presence_buffer.append(is_present)
        ratio = sum(self._presence_buffer) / len(self._presence_buffer)
        stable = ratio > PRESENCE_THRESHOLD
        if stable != self._last_presence:
            self.presence_changed_at = datetime.now(KST)
            self._last_presence = stable
        self.stable_presence = stable
        self.detected_at = timestamp
        self.latest_data = {"timestamp": timestamp}
        self.hardware_connected = True

    def update(self, row: dict, heart_rate: Optional[float] = None):
        raw_freq = row.get("dominant_freq_hz", 0)

        # EMA 스무딩
        if self._freq_ema is None:
            self._freq_ema = raw_freq
        else:
            self._freq_ema = EMA_ALPHA * raw_freq + (1 - EMA_ALPHA) * self._freq_ema
        self.smoothed_freq = self._freq_ema

        # presence debounce — RuView 값 그대로 사용
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

    async def broadcast_fall(self, data: dict):
        self.last_fall_data = data
        await self._send_all(self.fall_clients, data)


state = AppState()
