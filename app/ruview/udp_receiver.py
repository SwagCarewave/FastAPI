import argparse
import asyncio
import csv
import socket
import sys
from datetime import datetime, timezone, timedelta

from app.ruview.csi_parser import parse_csi
from app.ruview.presence_detector import detector
from app.ruview.state import state

UDP_IP = "0.0.0.0"
UDP_PORT = 5005
KST = timezone(timedelta(hours=9))


async def udp_receiver(label: str = "???", csv_writer=None):
    loop = asyncio.get_event_loop()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((UDP_IP, UDP_PORT))
    sock.setblocking(False)

    print(f"[UDP] Listening on {UDP_IP}:{UDP_PORT}... label={label}", flush=True)

    while True:
        try:
            data, addr = await loop.sock_recvfrom(sock, 65535)
            raw_str = data.decode("utf-8", errors="ignore")

            parsed = parse_csi(raw_str)
            if parsed is None:
                continue

            _, avg_var, window_std = detector.update(parsed["amplitudes"])
            timestamp = datetime.now(KST).isoformat()

            print(
                f"[DATA] avg_var={avg_var:.2f} | window_std={window_std:.2f} | rssi={parsed['rssi']} | label={label}",
                flush=True,
            )

            if csv_writer is not None:
                csv_writer.writerow([timestamp, avg_var, window_std, parsed["rssi"], label])

            state.update_from_csi(False, timestamp)

        except Exception as e:
            print(f"[UDP] Error: {e}", flush=True)
            await asyncio.sleep(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True, help="예: empty 또는 occupied")
    args = parser.parse_args()

    csv_path = f"csi_data_{args.label}.csv"
    csv_file = open(csv_path, "a", newline="", encoding="utf-8")
    writer = csv.writer(csv_file)

    if csv_file.tell() == 0:
        writer.writerow(["timestamp", "avg_var", "window_std", "rssi", "label"])

    print(f"[CSV] 저장 중: {csv_path}", flush=True)

    try:
        asyncio.run(udp_receiver(label=args.label, csv_writer=writer))
    finally:
        csv_file.close()
