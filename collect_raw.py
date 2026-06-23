"""
CSI Feature + Raw Collector

Usage:
    python3 collect_raw.py --label occupied
    python3 collect_raw.py --label unoccupied
    python3 collect_raw.py --label fall

Output:
    csi_features_<label>.csv  — 전처리된 feature
    csi_raw_<label>.csv       — 원시 서브캐리어 값
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


async def collect(label: str, experiment_id: str, feat_writer, raw_writer):
    loop = asyncio.get_event_loop()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((UDP_IP, UDP_PORT))
    sock.setblocking(False)

    print(f"[COLLECTOR] label={label}  port={UDP_PORT}  window={WINDOW_SIZE}", flush=True)
    print("[COLLECTOR] Ctrl+C to stop\n", flush=True)

    ant_bufs     = defaultdict(lambda: {"frames": [], "rssi": [], "win_count": 0})
    total_frames = 0
    raw_header_written = False
    raw_header_cols    = None

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
            timestamp = datetime.now(KST).isoformat()

            # ── Raw CSV 저장 (프레임 단위) ──────────────────────────────
            if not raw_header_written:
                raw_header_cols = ["experiment_id", "timestamp", "label", "rx"] + [f"sub_{i}" for i in range(len(amps))]
                raw_writer.writerow(raw_header_cols)
                raw_header_written = True

            raw_writer.writerow([experiment_id, timestamp, label, rx] + [round(a, 6) for a in amps])

            # ── Feature CSV 저장 (윈도우 단위) ─────────────────────────
            buf = ant_bufs[rx]
            buf["frames"].append(amps)
            buf["rssi"].append(parsed["rssi"] if parsed["rssi"] is not None else 0)
            total_frames += 1

            print(f"  [{total_frames}] {rx} rssi={parsed['rssi']} subs={len(amps)}", flush=True)

            for rx_label, b in ant_bufs.items():
                if len(b["frames"]) < WINDOW_SIZE:
                    continue
                feat = extract_features(b["frames"][:WINDOW_SIZE], b["rssi"][:WINDOW_SIZE])
                row  = [label, rx_label, b["win_count"] * WINDOW_SIZE] + [feat[k] for k in feat]
                feat_writer.writerow(row)
                b["win_count"] += 1
                b["frames"] = b["frames"][WINDOW_SIZE:]
                b["rssi"]   = b["rssi"][WINDOW_SIZE:]
                print(
                    f"[WIN {b['win_count']}] {rx_label} | "
                    f"amp={feat['amp_mean']:.3f} var={feat['window_var']:.4f}",
                    flush=True,
                )

        except Exception as e:
            import traceback
            print(f"[ERROR] {e}", flush=True)
            traceback.print_exc()
            await asyncio.sleep(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True, choices=["occupied", "unoccupied", "fall", "skeleton"])
    args = parser.parse_args()

    experiment_id = datetime.now(KST).strftime("%Y%m%d_%H%M%S")
    feat_path = f"csi_features_{args.label}.csv"
    raw_path  = f"csi_raw_{args.label}.csv"

    with open(feat_path, "w", newline="", encoding="utf-8") as ff, \
         open(raw_path,  "w", newline="", encoding="utf-8") as rf:

        feat_writer = csv.writer(ff)
        raw_writer  = csv.writer(rf)
        feat_writer.writerow(CSV_HEADER)

        print(f"[CSV] feature       → {feat_path}", flush=True)
        print(f"[CSV] raw           → {raw_path}",  flush=True)
        print(f"[CSV] experiment_id → {experiment_id}", flush=True)

        try:
            asyncio.run(collect(args.label, experiment_id, feat_writer, raw_writer))
        except KeyboardInterrupt:
            print(f"\n[DONE] 저장 완료: {feat_path}, {raw_path}", flush=True)
