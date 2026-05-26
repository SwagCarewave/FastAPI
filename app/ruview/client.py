import asyncio
import websockets
import json
import csv
import os
from datetime import datetime, timezone, timedelta
from typing import Optional
from app.ruview.state import state, KST

RUVIEW_WS_URL = "ws://43.201.215.82:3001/ws/sensing"
CSV_PATH = "csi_data.csv"

FIELDNAMES = [
    "timestamp",
    "variance",
    "motion_band_power",
    "breathing_band_power",
    "dominant_freq_hz",
    "change_points",
    "spectral_power",
    "presence",
    "motion_level",
]


def init_csv():
    if not os.path.exists(CSV_PATH):
        with open(CSV_PATH, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()


def save_row(row: dict):
    with open(CSV_PATH, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writerow(row)


async def ruview_listener():
    init_csv()
    print(f"RuView WebSocket 연결 중: {RUVIEW_WS_URL}")
    while True:
        try:
            async with websockets.connect(RUVIEW_WS_URL) as ws:
                print("RuView 연결 완료. 데이터 수신 중...")
                count = 0
                while True:
                    raw = await ws.recv()
                    data = json.loads(raw)

                    node_features = data.get("node_features", [])
                    if not node_features:
                        continue

                    node = node_features[0]
                    features = node.get("features", {})
                    classification = node.get("classification", {})

                    vital_signs = data.get("vital_signs") or {}
                    heart_rate: Optional[float] = vital_signs.get("heart_rate_bpm")

                    row = {
                        "timestamp": datetime.now(KST).isoformat(),
                        "variance": features.get("variance", 0),
                        "motion_band_power": features.get("motion_band_power", 0),
                        "breathing_band_power": features.get("breathing_band_power", 0),
                        "dominant_freq_hz": features.get("dominant_freq_hz", 0),
                        "change_points": features.get("change_points", 0),
                        "spectral_power": features.get("spectral_power", 0),
                        "presence": classification.get("presence", False),
                        "motion_level": classification.get("motion_level", ""),
                    }

                    save_row(row)
                    state.update(row, heart_rate)

                    count += 1
                    if count % 50 == 0:
                        print(f"[{count}프레임] variance={row['variance']:.2f} presence={row['presence']}")

                    hw = state.hardware_connected

                    await state.broadcast({**row, "hardware_connected": hw})

                    breathing_rate = round(state.smoothed_freq * 60) if state.stable_presence else None
                    hr = heart_rate if state.stable_presence else None

                    await state.broadcast_breathing({
                        "breathing_rate": breathing_rate,
                        "heart_rate": hr,
                        "timestamp": row["timestamp"],
                        "hardware_connected": hw,
                    })

                    await state.broadcast_presence({
                        "is_present": state.stable_presence,
                        "status": "재실" if state.stable_presence else "공실",
                        "detected_at": state.detected_at,
                        "hardware_connected": hw,
                    })

        except Exception as e:
            print(f"RuView 연결 끊김: {e}. 3초 후 재연결...")
            await asyncio.sleep(3)
