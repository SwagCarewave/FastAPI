import argparse
import asyncio
import csv
import os
import socket
from datetime import datetime, timezone, timedelta

import httpx
from dotenv import load_dotenv

from app.ruview.csi_parser import parse_csi
from app.ruview.presence_detector import detector, AVG_VAR_THRESHOLD, WINDOW_STD_THRESHOLD, FRAME_DIFF_THRESHOLD
from app.ruview.state import state

load_dotenv()

UDP_IP = "0.0.0.0"
UDP_PORT = 5005
KST = timezone(timedelta(hours=9))

SPRINGBOOT_URL = os.getenv("SPRINGBOOT_URL", "")
ROOM = os.getenv("ROOM", "101호")
FALL_COOLDOWN_SEC = 60  # 낙상 이벤트 최소 간격 (스팸 방지)


def judge(avg_var: float, window_std: float, frame_diff: float) -> tuple[bool, str]:
    if avg_var >= AVG_VAR_THRESHOLD:
        return False, "공실"
    if window_std >= WINDOW_STD_THRESHOLD and frame_diff >= FRAME_DIFF_THRESHOLD:
        return True, "움직임감지"
    return True, "재실"


async def send_fall_event(occurred_at: str):
    if not SPRINGBOOT_URL:
        print("[EVENT] SPRINGBOOT_URL 미설정 — Spring Boot 전송 생략", flush=True)
        return

    payload = {
        "event_type": "낙상 감지",
        "occurred_at": occurred_at,
        "status": "미확인",
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(f"{SPRINGBOOT_URL}/api/events", json=payload)
            print(f"[EVENT] Spring Boot 전송 완료 ({resp.status_code})", flush=True)
    except Exception as e:
        print(f"[EVENT] Spring Boot 전송 실패: {e}", flush=True)


def _fall_cooldown_ok() -> bool:
    if state.last_fall_event_at is None:
        return True
    elapsed = (datetime.now(KST) - state.last_fall_event_at).total_seconds()
    return elapsed >= FALL_COOLDOWN_SEC


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

            _, avg_var, window_std, frame_diff = detector.update(parsed["amplitudes"])
            rssi = parsed["rssi"]
            timestamp = datetime.now(KST).isoformat()

            is_present, status = judge(avg_var, window_std, frame_diff)

            print(
                f"[PRESENCE] {status} | avg_var={avg_var:.2f} | window_std={window_std:.2f} | frame_diff={frame_diff:.3f} | rssi={rssi}",
                flush=True,
            )

            if csv_writer is not None:
                csv_writer.writerow([timestamp, avg_var, window_std, frame_diff, rssi, label])

            state.update_from_csi(is_present, timestamp)

            presence_data = {
                "status": "재실" if state.stable_presence else "공실",
                "detected_at": timestamp,
            }
            await state.broadcast_presence(presence_data)

            # 낙상 감지 이벤트 — 별도 채널로 분리
            if status == "움직임감지" and _fall_cooldown_ok():
                state.last_fall_event_at = datetime.now(KST)
                state.set_fall_lock(30)

                fall_data = {
                    "event_type": "낙상 감지",
                    "occurred_at": timestamp,
                    "status": "미확인",
                }
                print(f"[EVENT] 낙상 감지 — {timestamp}", flush=True)

                asyncio.create_task(send_fall_event(timestamp))
                await state.broadcast_fall(fall_data)

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
        writer.writerow(["timestamp", "avg_var", "window_std", "frame_diff", "rssi", "label"])

    print(f"[CSV] 저장 중: {csv_path}", flush=True)

    try:
        asyncio.run(udp_receiver(label=args.label, csv_writer=writer))
    finally:
        csv_file.close()
