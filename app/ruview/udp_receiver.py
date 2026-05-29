import argparse
import asyncio
import csv
import socket
from datetime import datetime, timezone, timedelta

from app.ruview.csi_parser import parse_csi
from app.ruview.presence_detector import detector
from app.ruview.state import state

UDP_IP = "0.0.0.0"
UDP_PORT = 5005
KST = timezone(timedelta(hours=9))

RSSI_THRESHOLD = -60  # rssi >= -60 → 재실, < -60 → 공실


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
            rssi = parsed["rssi"]
            timestamp = datetime.now(KST).isoformat()

            is_present = rssi >= RSSI_THRESHOLD
            status = "재실" if is_present else "공실"

            print(
                f"[PRESENCE] {status} | avg_var={avg_var:.2f} | window_std={window_std:.2f} | rssi={rssi}",
                flush=True,
            )

            if csv_writer is not None:
                csv_writer.writerow([timestamp, avg_var, window_std, rssi, label])

            state.update_from_csi(is_present, timestamp)

            presence_data = {
                "is_present": state.stable_presence,
                "status": "재실" if state.stable_presence else "공실",
                "detected_at": timestamp,
            }
            await state.broadcast_presence(presence_data)
            await state.broadcast(presence_data)

        except Exception as e:
            print(f"[UDP] Error: {e}", flush=True)
            await asyncio.sleep(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True, help="예: empty, occupied, fall")
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
