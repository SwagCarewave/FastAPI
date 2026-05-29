import asyncio
import socket
from datetime import datetime, timezone, timedelta

from app.ruview.csi_parser import parse_csi
from app.ruview.presence_detector import detector
from app.ruview.state import state

UDP_IP = "0.0.0.0"
UDP_PORT = 5005
KST = timezone(timedelta(hours=9))


async def udp_receiver():
    loop = asyncio.get_event_loop()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((UDP_IP, UDP_PORT))
    sock.setblocking(False)

    print(f"[UDP] Listening on {UDP_IP}:{UDP_PORT}...", flush=True)

    while True:
        try:
            data, addr = await loop.sock_recvfrom(sock, 65535)
            raw_str = data.decode("utf-8", errors="ignore")
            print(f"\n[UDP] FROM: {addr}", flush=True)
            print(raw_str, flush=True)

            parsed = parse_csi(raw_str)
            if parsed is None:
                continue

            is_present, avg_var = detector.update(parsed["amplitudes"])
            timestamp = datetime.now(KST).isoformat()

            state.update_from_csi(is_present, timestamp)

            presence_data = {
                "is_present": state.stable_presence,
                "status": "재실" if state.stable_presence else "공실",
                "detected_at": timestamp,
            }
            print(f"[PRESENCE] {presence_data['status']} | avg_var={avg_var:.4f} | rssi={parsed['rssi']}", flush=True)

            await state.broadcast_presence(presence_data)
            await state.broadcast(presence_data)

        except Exception as e:
            print(f"[UDP] Error: {e}", flush=True)
            await asyncio.sleep(1)
