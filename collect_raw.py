"""
Raw CSI data collector — completely standalone, no detection logic.

Usage:
    python3 collect_raw.py --label occupied   # 재실
    python3 collect_raw.py --label unoccupied # 비재실
    python3 collect_raw.py --label fall       # 낙상

Output: csi_raw_<label>.csv
    timestamp, raw_csi, label
"""

import argparse
import asyncio
import csv
import socket
from datetime import datetime, timezone, timedelta

UDP_IP = "0.0.0.0"
UDP_PORT = 5005
KST = timezone(timedelta(hours=9))


async def collect(label: str, csv_writer):
    loop = asyncio.get_event_loop()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((UDP_IP, UDP_PORT))
    sock.setblocking(False)

    print(f"[RAW COLLECTOR] label={label}  port={UDP_PORT}", flush=True)
    print("[RAW COLLECTOR] Ctrl+C to stop\n", flush=True)

    frame_count = 0
    while True:
        try:
            data, addr = await loop.sock_recvfrom(sock, 65535)
            raw_str = data.decode("utf-8", errors="ignore").strip()

            if not raw_str:
                continue

            timestamp = datetime.now(KST).isoformat()
            csv_writer.writerow([timestamp, raw_str, label])

            frame_count += 1
            if frame_count % 50 == 0:
                print(f"[{frame_count} frames] {timestamp}", flush=True)
            else:
                print(f"  {raw_str[:80]}...", flush=True)

        except Exception as e:
            print(f"[ERROR] {e}", flush=True)
            await asyncio.sleep(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--label",
        required=True,
        choices=["occupied", "unoccupied", "fall"],
        help="수집 레이블: occupied / unoccupied / fall",
    )
    args = parser.parse_args()

    csv_path = f"csi_raw_{args.label}.csv"

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "raw_csi", "label"])

        print(f"[CSV] {csv_path} 저장 시작", flush=True)
        try:
            asyncio.run(collect(args.label, writer))
        except KeyboardInterrupt:
            print(f"\n[DONE] 저장 완료: {csv_path}", flush=True)
