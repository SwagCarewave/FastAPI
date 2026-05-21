import asyncio
import websockets
import json
import csv
import os
from datetime import datetime

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


async def subscribe():
    init_csv()
    print(f"RuView WebSocket 연결 중: {RUVIEW_WS_URL}")
    print(f"CSV 저장 경로: {CSV_PATH}")
    print("Ctrl+C로 중지")

    async with websockets.connect(RUVIEW_WS_URL) as ws:
        print("연결 완료. 데이터 수신 중...")
        count = 0
        while True:
            try:
                raw = await ws.recv()
                data = json.loads(raw)

                node_features = data.get("node_features", [])
                if not node_features:
                    continue

                # 첫 번째 노드 데이터 사용
                node = node_features[0]
                features = node.get("features", {})
                classification = node.get("classification", {})

                row = {
                    "timestamp": datetime.now().timestamp(),
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
                count += 1
                if count % 50 == 0:
                    print(f"[{count}프레임 저장됨] variance={row['variance']:.2f} motion={row['motion_band_power']:.2f}")

            except Exception as e:
                print(f"에러: {e}")
                break


if __name__ == "__main__":
    asyncio.run(subscribe())
