"""
CSI Feature Collector — preprocessing + feature extraction per window

Usage:
    python3 collect_raw.py --label occupied
    python3 collect_raw.py --label unoccupied
    python3 collect_raw.py --label fall

Output: csi_features_<label>.csv
    label, rx, start,
    rssi_mean, rssi_std, amp_mean, amp_std_time,
    subcarrier_var_mean, subcarrier_std_mean,
    temporal_diff_mean_abs, temporal_diff_std,
    window_var, spectral_total_power,
    low_band_ratio, mid_band_ratio, dominant_freq_idx, corr_mean_abs,
    spectral_entropy, peak_to_peak, skewness, kurtosis
"""

import argparse
import asyncio
import csv
import math
import re
import socket
from collections import defaultdict
from datetime import datetime, timezone, timedelta

import numpy as np

UDP_IP = "0.0.0.0"
UDP_PORT = 5005
KST = timezone(timedelta(hours=9))

WINDOW_SIZE = 100
FFT_N = 128

HAMPEL_HALF_WIN = 5
HAMPEL_SIGMA = 3.0
MA_WIN = 5

LOW_CUTOFF = 0.1
MID_CUTOFF = 0.4

CSV_HEADER = [
    "label", "rx", "start",
    "rssi_mean", "rssi_std",
    "amp_mean", "amp_std_time",
    "subcarrier_var_mean", "subcarrier_std_mean",
    "temporal_diff_mean_abs", "temporal_diff_std",
    "window_var", "spectral_total_power",
    "low_band_ratio", "mid_band_ratio",
    "dominant_freq_idx", "corr_mean_abs",
    "spectral_entropy",
    "peak_to_peak",
    "skewness",
    "kurtosis",
]

# ── Parsing ──────────────────────────────────────────────────────────────────

def parse_csi(raw: str) -> dict | None:
    """ESP32 CSI UDP 패킷 → amplitudes + RSSI + 안테나 인덱스."""
    match = re.search(r'\[([^\]]+)\]', raw)
    if not match:
        return None
    try:
        nums = list(map(int, match.group(1).split()))
    except ValueError:
        return None
    if len(nums) < 4:
        return None

    amplitudes = []
    for i in range(0, len(nums) - 1, 2):
        amp = math.sqrt(nums[i] ** 2 + nums[i + 1] ** 2)
        if amp > 0:  # 순수 0(guard/null subcarrier)만 제외
            amplitudes.append(amp)

    if not amplitudes:
        return None

    parts = raw.split(',')
    try:
        rssi = int(parts[3])
    except (IndexError, ValueError):
        rssi = None

    # ESP32 CSI 포맷: ant 필드는 인덱스 19
    try:
        ant = int(parts[19])
    except (IndexError, ValueError):
        ant = 0

    return {"amplitudes": amplitudes, "rssi": rssi, "ant": ant}


# ── Preprocessing ─────────────────────────────────────────────────────────────

def hampel_filter(x: np.ndarray) -> np.ndarray:
    out = x.copy()
    n = len(x)
    for i in range(n):
        lo = max(0, i - HAMPEL_HALF_WIN)
        hi = min(n, i + HAMPEL_HALF_WIN + 1)
        win = x[lo:hi]
        med = np.median(win)
        mad = np.median(np.abs(win - med)) * 1.4826
        if mad > 0 and abs(x[i] - med) > HAMPEL_SIGMA * mad:
            out[i] = med
    return out


def moving_average(x: np.ndarray) -> np.ndarray:
    return np.convolve(x, np.ones(MA_WIN) / MA_WIN, mode='same')


# ── Feature Extraction ────────────────────────────────────────────────────────

def extract_features(frames: list, rssi_list: list, start: int, label: str, rx: str) -> list:
    min_subs = min(len(f) for f in frames)
    amp_matrix = np.array([f[:min_subs] for f in frames], dtype=float)
    rssi_arr = np.array(rssi_list, dtype=float)

    amp_filtered = np.apply_along_axis(hampel_filter, 0, amp_matrix)
    amp_smooth   = np.apply_along_axis(moving_average, 0, amp_filtered)
    frame_means  = amp_smooth.mean(axis=1)

    # RSSI
    valid_rssi = rssi_arr[rssi_arr != 0]
    rssi_mean = float(np.mean(valid_rssi)) if len(valid_rssi) > 0 else 0.0
    rssi_std  = float(np.std(valid_rssi))  if len(valid_rssi) > 0 else 0.0

    # Amplitude
    amp_mean     = float(np.mean(amp_smooth))
    amp_std_time = float(np.std(frame_means))

    # Subcarrier spatial
    subcarrier_var_mean = float(np.mean(np.var(amp_smooth, axis=1)))
    subcarrier_std_mean = float(np.mean(np.std(amp_smooth, axis=1)))

    # Temporal diff
    diffs = np.diff(frame_means)
    temporal_diff_mean_abs = float(np.mean(np.abs(diffs)))
    temporal_diff_std      = float(np.std(diffs))

    # Window variance
    signal     = frame_means - frame_means.mean()
    window_var = float(np.var(signal))
    spectral_total_power = window_var

    # FFT
    fft_vals  = np.fft.rfft(signal, n=FFT_N)
    fft_power = np.abs(fft_vals) ** 2
    freqs     = np.fft.rfftfreq(FFT_N)

    pos_mask  = freqs > 0
    total_pos = float(np.sum(fft_power[pos_mask])) or 1.0

    low_band_ratio = float(np.sum(fft_power[(freqs > 0) & (freqs <= LOW_CUTOFF)])) / total_pos
    mid_band_ratio = float(np.sum(fft_power[(freqs > LOW_CUTOFF) & (freqs <= MID_CUTOFF)])) / total_pos

    dom_idx_in_pos  = int(np.argmax(fft_power[pos_mask]))
    dominant_freq_idx = float(freqs[pos_mask][dom_idx_in_pos])

    # PCA (SVD) — 주성분 방향 추출, 향후 활용 가능
    try:
        amp_centered = amp_smooth - amp_smooth.mean(axis=0)
        _, _, Vt = np.linalg.svd(amp_centered, full_matrices=False)
        _pc1 = Vt[0]  # noqa: F841
    except np.linalg.LinAlgError:
        pass

    # Subcarrier correlation
    if min_subs > 1:
        corr_matrix = np.corrcoef(amp_smooth.T)
        upper = np.triu(np.ones_like(corr_matrix, dtype=bool), k=1)
        corr_mean_abs = float(np.mean(np.abs(corr_matrix[upper])))
    else:
        corr_mean_abs = 0.0

    # ── 추가 특징 ──────────────────────────────────────────────────────────────

    # Spectral Entropy: 스펙트럼 분포의 불확실성 (사람 존재 시 증가)
    prob = fft_power[pos_mask] / total_pos
    spectral_entropy = float(-np.sum(prob * np.log2(prob + 1e-12)))

    # Peak-to-Peak: 움직임 크기 직접 반영
    peak_to_peak = float(np.max(frame_means) - np.min(frame_means))

    # Skewness (왜도): 3차 표준화 모멘트
    std = float(np.std(signal)) or 1e-10
    skewness = float(np.mean(((signal - signal.mean()) / std) ** 3))

    # Kurtosis (첨도): 4차 표준화 모멘트 — 3 (excess kurtosis)
    kurtosis = float(np.mean(((signal - signal.mean()) / std) ** 4) - 3)

    return [
        label, rx, start,
        rssi_mean, rssi_std,
        amp_mean, amp_std_time,
        subcarrier_var_mean, subcarrier_std_mean,
        temporal_diff_mean_abs, temporal_diff_std,
        window_var, spectral_total_power,
        low_band_ratio, mid_band_ratio,
        dominant_freq_idx, corr_mean_abs,
        spectral_entropy, peak_to_peak, skewness, kurtosis,
    ]


# ── Collection loop ───────────────────────────────────────────────────────────

async def collect(label: str, csv_writer):
    loop = asyncio.get_event_loop()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((UDP_IP, UDP_PORT))
    sock.setblocking(False)

    print(f"[FEATURE COLLECTOR] label={label}  port={UDP_PORT}", flush=True)
    print(f"[FEATURE COLLECTOR] window={WINDOW_SIZE} frames | FFT_N={FFT_N}", flush=True)
    print("[FEATURE COLLECTOR] Ctrl+C to stop\n", flush=True)

    # 안테나별 독립 버퍼: {ant_idx: {"frames": [], "rssi": [], "win_count": 0}}
    ant_bufs: dict = defaultdict(lambda: {"frames": [], "rssi": [], "win_count": 0})
    total_frames = 0

    while True:
        try:
            data, _ = await loop.sock_recvfrom(sock, 65535)
            raw_str = data.decode("utf-8", errors="ignore").strip()
            if not raw_str:
                continue

            parsed = parse_csi(raw_str)
            if parsed is None:
                continue

            ant = parsed["ant"]
            buf = ant_bufs[ant]
            buf["frames"].append(parsed["amplitudes"])
            buf["rssi"].append(parsed["rssi"] if parsed["rssi"] is not None else 0)
            total_frames += 1

            print(f"  [{total_frames}] RX{ant+1} rssi={parsed['rssi']} subs={len(parsed['amplitudes'])}", flush=True)

            # 윈도우가 꽉 찬 안테나 처리
            for a, b in ant_bufs.items():
                if len(b["frames"]) < WINDOW_SIZE:
                    continue
                rx_label  = f"RX{a + 1}"
                start_idx = b["win_count"] * WINDOW_SIZE
                row = extract_features(b["frames"][:WINDOW_SIZE], b["rssi"][:WINDOW_SIZE], start_idx, label, rx_label)
                csv_writer.writerow(row)
                b["win_count"] += 1
                b["frames"] = b["frames"][WINDOW_SIZE:]
                b["rssi"]   = b["rssi"][WINDOW_SIZE:]
                print(
                    f"[WIN {b['win_count']}] {rx_label} start={start_idx} | "
                    f"amp_mean={row[5]:.3f} win_var={row[11]:.4f} entropy={row[17]:.3f} p2p={row[18]:.3f}",
                    flush=True,
                )

        except Exception as e:
            import traceback
            print(f"[ERROR] {e}", flush=True)
            traceback.print_exc()
            await asyncio.sleep(1)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--label",
        required=True,
        choices=["occupied", "unoccupied", "fall"],
    )
    args = parser.parse_args()

    csv_path = f"csi_features_{args.label}.csv"

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADER)
        print(f"[CSV] {csv_path} 저장 시작", flush=True)
        try:
            asyncio.run(collect(args.label, writer))
        except KeyboardInterrupt:
            print(f"\n[DONE] 저장 완료: {csv_path}", flush=True)
