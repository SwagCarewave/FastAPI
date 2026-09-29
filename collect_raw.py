"""
CSI Feature + Raw Collector

Usage:
    python3 collect_raw.py --label occupied
    python3 collect_raw.py --label unoccupied
    python3 collect_raw.py --label fall

Output:
    csi_features_<label>.csv  — 전처리된 feature (수집 종료 후 raw로부터 생성)
    csi_raw_<label>.csv       — 원시 서브캐리어 값 (experiment_id,timestamp,label,rx,sub_0..sub_51 — 외부 모델 호환용, 형식 고정)
    csi_raw_<label>_rssi.csv  — raw와 같은 순서의 rssi 값 (feature 재계산용 보조 파일)
"""
import argparse
import asyncio
import csv
import socket
from collections import defaultdict
from datetime import datetime, timezone, timedelta

from app.csi.feature_extractor import (
    parse_csi, extract_features,
    WINDOW_SIZE, CSV_HEADER,
)

UDP_IP   = "0.0.0.0"
UDP_PORT = 5005
KST      = timezone(timedelta(hours=9))


async def collect(label: str, experiment_id: str, raw_writer, rssi_writer):
    """raw CSI만 받아서 저장. feature 계산은 수집 루프를 막지 않도록 종료 후 별도 처리."""
    loop = asyncio.get_event_loop()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((UDP_IP, UDP_PORT))
    sock.setblocking(False)

    print(f"[COLLECTOR] label={label}  port={UDP_PORT}  window={WINDOW_SIZE}", flush=True)
    print("[COLLECTOR] Ctrl+C to stop\n", flush=True)

    total_frames = 0
    raw_header_written = False

    while True:
        try:
            data, _ = await loop.sock_recvfrom(sock, 65535)
            raw_str  = data.decode("utf-8", errors="ignore").strip()
            if not raw_str:
                continue

            parsed = parse_csi(raw_str)
            if parsed is None:
                continue

            rx        = parsed["rx"]
            amps      = parsed["amplitudes"]
            rssi      = parsed["rssi"] if parsed["rssi"] is not None else 0
            timestamp = datetime.now(KST).isoformat()

            # ── raw CSV: 형식 고정 (외부 모델 전처리가 이 순서를 그대로 읽음) ──
            if not raw_header_written:
                raw_header_cols = ["experiment_id", "timestamp", "label", "rx"] + [f"sub_{i}" for i in range(len(amps))]
                raw_writer.writerow(raw_header_cols)
                raw_header_written = True

            raw_writer.writerow([experiment_id, timestamp, label, rx] + [round(a, 6) for a in amps])

            # ── rssi 보조 파일: raw와 같은 행 순서로 rx, rssi만 저장 ──
            rssi_writer.writerow([rx, rssi])

            total_frames += 1
            print(f"  [{total_frames}] {rx} rssi={parsed['rssi']} subs={len(amps)}", flush=True)

        except Exception as e:
            import traceback
            print(f"[ERROR] {e}", flush=True)
            traceback.print_exc()
            await asyncio.sleep(1)


def build_features(raw_path: str, rssi_path: str, feat_path: str, label: str):
    """수집이 끝난 raw CSV(+rssi 보조 파일)를 읽어 WINDOW_SIZE 단위로 feature CSV를 생성."""
    ant_bufs = defaultdict(lambda: {"frames": [], "rssi": [], "win_count": 0})

    with open(raw_path, newline="", encoding="utf-8") as rf, \
         open(rssi_path, newline="", encoding="utf-8") as sf:
        raw_reader  = csv.reader(rf)
        rssi_reader = csv.reader(sf)
        next(raw_reader, None)  # header

        for row, (rssi_rx, rssi_val) in zip(raw_reader, rssi_reader):
            rx   = row[3]
            amps = [float(x) for x in row[4:] if x != ""]
            ant_bufs[rx]["frames"].append(amps)
            ant_bufs[rx]["rssi"].append(float(rssi_val) if rssi_val != "" else 0)

    with open(feat_path, "w", newline="", encoding="utf-8") as ff:
        feat_writer = csv.writer(ff)
        feat_writer.writerow(CSV_HEADER)

        for rx_label, b in ant_bufs.items():
            frames, rssi_list = b["frames"], b["rssi"]
            win_count = 0
            while len(frames) >= WINDOW_SIZE:
                feat = extract_features(frames[:WINDOW_SIZE], rssi_list[:WINDOW_SIZE])
                row  = [label, rx_label, win_count * WINDOW_SIZE] + [feat[k] for k in feat]
                feat_writer.writerow(row)
                win_count += 1
                frames    = frames[WINDOW_SIZE:]
                rssi_list = rssi_list[WINDOW_SIZE:]

    print(f"[FEATURE] {feat_path} 생성 완료", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True, choices=["occupied", "unoccupied", "fall", "skeleton"])
    args = parser.parse_args()

    experiment_id = datetime.now(KST).strftime("%Y%m%d_%H%M%S")
    feat_path = f"csi_features_{args.label}.csv"
    raw_path  = f"csi_raw_{args.label}.csv"
    rssi_path = f"csi_raw_{args.label}_rssi.csv"

    with open(raw_path, "w", newline="", encoding="utf-8") as rf, \
         open(rssi_path, "w", newline="", encoding="utf-8") as sf:
        raw_writer  = csv.writer(rf)
        rssi_writer = csv.writer(sf)

        print(f"[CSV] raw           → {raw_path}",  flush=True)
        print(f"[CSV] experiment_id → {experiment_id}", flush=True)

        try:
            asyncio.run(collect(args.label, experiment_id, raw_writer, rssi_writer))
        except KeyboardInterrupt:
            print(f"\n[DONE] raw 저장 완료: {raw_path}", flush=True)

    build_features(raw_path, rssi_path, feat_path, args.label)
    print(f"[DONE] feature 저장 완료: {feat_path}", flush=True)
