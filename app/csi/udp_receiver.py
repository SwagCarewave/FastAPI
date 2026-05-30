import asyncio
import os
import socket
from collections import defaultdict, deque
from datetime import datetime, timezone, timedelta

import httpx
from dotenv import load_dotenv

from app.csi.feature_extractor import parse_csi, extract_features, WINDOW_SIZE
from app.csi.ml_predictor import predictor
from app.csi.presence_detector import detector, FRAME_DIFF_THRESHOLD
from app.csi.state import state

load_dotenv()

UDP_IP  = "0.0.0.0"
UDP_PORT = 5005
KST     = timezone(timedelta(hours=9))

SPRINGBOOT_URL      = os.getenv("SPRINGBOOT_URL", "")
FALL_COOLDOWN_SEC   = 60
FALL_CONFIRM_FRAMES = 2
CONFIDENCE_THRESHOLD = 0.80   # 재실 판정 최소 신뢰도
UNOCCUPIED_CONFIRM   = 2      # 공실 전환에 필요한 연속 예측 횟수
WINDOW_STEP          = 25     # 슬라이딩 윈도우 간격 (예측 주기)

_fall_candidate_count = 0


# ── 낙상 이벤트 ───────────────────────────────────────────────────────────────

async def _send_fall_event(occurred_at: str):
    if not SPRINGBOOT_URL:
        print("[EVENT] SPRINGBOOT_URL 미설정 — Spring Boot 전송 생략", flush=True)
        return
    payload = {"event_type": "낙상 감지", "occurred_at": occurred_at, "status": "미확인"}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(f"{SPRINGBOOT_URL}/api/events", json=payload)
            print(f"[EVENT] Spring Boot 전송 완료 ({resp.status_code})", flush=True)
    except Exception as e:
        print(f"[EVENT] Spring Boot 전송 실패: {e}", flush=True)


def _fall_cooldown_ok() -> bool:
    if state.last_fall_event_at is None:
        return True
    return (datetime.now(KST) - state.last_fall_event_at).total_seconds() >= FALL_COOLDOWN_SEC


# ── UDP 수신 루프 ─────────────────────────────────────────────────────────────

async def udp_receiver():
    loop = asyncio.get_event_loop()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((UDP_IP, UDP_PORT))
    sock.setblocking(False)

    print(f"[UDP] Listening on {UDP_IP}:{UDP_PORT}", flush=True)
    print(f"[UDP] ML 모델 준비: {predictor.ready} | step={WINDOW_STEP}프레임마다 예측", flush=True)

    # 슬라이딩 윈도우 버퍼 (maxlen=WINDOW_SIZE → 자동으로 오래된 프레임 제거)
    ant_bufs = defaultdict(lambda: {
        "frames":         deque(maxlen=WINDOW_SIZE),
        "rssi":           deque(maxlen=WINDOW_SIZE),
        "since_last_pred": 0,   # 마지막 예측 이후 수신 프레임 수
    })

    ant_predictions:      dict[str, bool] = {}
    ant_unoccupied_streak: dict[str, int] = defaultdict(int)

    global _fall_candidate_count

    while True:
        try:
            data, _ = await loop.sock_recvfrom(sock, 65535)
            raw_str   = data.decode("utf-8", errors="ignore")
            timestamp = datetime.now(KST).isoformat()

            parsed = parse_csi(raw_str)
            if parsed is None:
                continue

            rx  = parsed["rx"]
            buf = ant_bufs[rx]
            buf["frames"].append(parsed["amplitudes"])
            buf["rssi"].append(parsed["rssi"] if parsed["rssi"] is not None else 0)
            buf["since_last_pred"] += 1

            # ── 낙상 감지 (프레임 단위) ───────────────────────────────────────
            _, _, _, frame_diff = detector.update(parsed["amplitudes"])

            if frame_diff >= FRAME_DIFF_THRESHOLD:
                _fall_candidate_count += 1
            else:
                _fall_candidate_count = 0

            if _fall_candidate_count >= FALL_CONFIRM_FRAMES and _fall_cooldown_ok():
                _fall_candidate_count = 0
                state.last_fall_event_at = datetime.now(KST)
                state.set_fall_lock(30)
                fall_data = {"event_type": "낙상 감지", "occurred_at": timestamp, "status": "미확인"}
                print(f"[EVENT] 낙상 감지 — {timestamp}", flush=True)
                asyncio.create_task(_send_fall_event(timestamp))
                await state.broadcast_fall(fall_data)

            # ── ML 재실 예측 (슬라이딩 윈도우) ──────────────────────────────
            if len(buf["frames"]) < WINDOW_SIZE:
                continue
            if buf["since_last_pred"] < WINDOW_STEP:
                continue

            buf["since_last_pred"] = 0
            feat_dict   = extract_features(list(buf["frames"]), list(buf["rssi"]))
            is_occupied, confidence = predictor.predict(feat_dict, rx)

            if is_occupied:
                if confidence >= CONFIDENCE_THRESHOLD:
                    ant_predictions[rx] = True
                    ant_unoccupied_streak[rx] = 0
                else:
                    is_occupied = ant_predictions.get(rx, True)
                    print(f"[ML] {rx} 낮은 신뢰도({confidence:.2f}) 재실 — 이전 상태 유지", flush=True)
            else:
                ant_unoccupied_streak[rx] += 1
                if ant_unoccupied_streak[rx] >= UNOCCUPIED_CONFIRM:
                    ant_predictions[rx] = False
                else:
                    is_occupied = ant_predictions.get(rx, False)
                    print(f"[ML] {rx} 공실 예측 {ant_unoccupied_streak[rx]}/{UNOCCUPIED_CONFIRM}번째", flush=True)

            votes        = list(ant_predictions.values())
            final_result = sum(votes) > len(votes) / 2
            status_str   = "재실" if final_result else "공실"

            print(
                f"[ML] {rx} → {'재실' if is_occupied else '공실'} "
                f"(conf={confidence:.2f}) | 종합={status_str}",
                flush=True,
            )

            state.update_from_csi(final_result, timestamp)
            await state.broadcast_presence({
                "status":      status_str,
                "confidence":  round(confidence, 4),
                "rx":          rx,
                "detected_at": timestamp,
            })

        except Exception as e:
            import traceback
            print(f"[UDP] Error: {e}", flush=True)
            traceback.print_exc()
            await asyncio.sleep(1)
