"""
CSI Feature Collector — preprocessing + feature extraction per window

Usage:
    python3 collect_raw.py --label occupied
    python3 collect_raw.py --label unoccupied
    python3 collect_raw.py --label fall

Output: csi_features_<label>.csv
    label, rx, start,
    rssi_mean, rssi_std,
    amp_mean, amp_std_time,
    subcarrier_var_mean, subcarrier_std_mean,
    temporal_diff_mean_abs, temporal_diff_std,
    window_var, spectral_total_power,
    low_band_ratio, mid_band_ratio,
    dominant_freq_idx, corr_mean_abs
"""

import argparse
import asyncio
import csv
import math
import re
import socket
from datetime import datetime, timezone, timedelta

import numpy as np

UDP_IP = "0.0.0.0"
UDP_PORT = 5005
KST = timezone(timedelta(hours=9))

# Window settings
WINDOW_SIZE = 100   # frames per feature window (non-overlapping)
FFT_N = 128         # zero-pad size for FFT (power-of-2)

# Hampel filter
HAMPEL_HALF_WIN = 5
HAMPEL_SIGMA = 3.0

# Moving average
MA_WIN = 5

# FFT band definitions (normalized frequency 0–0.5)
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
]


# ── Parsing ─────────────────────────────────────────────────────────────────

def parse_csi(raw: str) -> dict | None:
    """Parse ESP32 CSI UDP packet → amplitudes + RSSI."""
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
        if amp > 1.0:  # guard / null subcarrier 제외
            amplitudes.append(amp)

    if not amplitudes:
        return None

    parts = raw.split(',')
    try:
        rssi = int(parts[3])
    except (IndexError, ValueError):
        rssi = None

    return {"amplitudes": amplitudes, "rssi": rssi}


# ── Preprocessing ────────────────────────────────────────────────────────────

def hampel_filter(x: np.ndarray) -> np.ndarray:
    """Hampel identifier: replace outliers with local median."""
    out = x.copy()
    n = len(x)
    for i in range(n):
        lo = max(0, i - HAMPEL_HALF_WIN)
        hi = min(n, i + HAMPEL_HALF_WIN + 1)
        win = x[lo:hi]
        med = np.median(win)
        mad = np.median(np.abs(win - med)) * 1.4826  # scaled MAD ≈ σ
        if mad > 0 and abs(x[i] - med) > HAMPEL_SIGMA * mad:
            out[i] = med
    return out


def moving_average(x: np.ndarray) -> np.ndarray:
    return np.convolve(x, np.ones(MA_WIN) / MA_WIN, mode='same')


# ── Feature Extraction ───────────────────────────────────────────────────────

def extract_features(frames: list[list[float]], rssi_list: list[float], start: int, label: str) -> list:
    """
    frames : list of amplitude arrays per frame (length may vary)
    rssi_list : RSSI per frame
    start : frame index at window start
    """
    # Align subcarrier count across frames
    min_subs = min(len(f) for f in frames)
    amp_matrix = np.array([f[:min_subs] for f in frames], dtype=float)  # (N, S)
    rssi_arr = np.array(rssi_list, dtype=float)

    # ── Preprocessing ────────────────────────────────────────────────────────
    # Hampel filter then moving average on each subcarrier time series
    amp_filtered = np.apply_along_axis(hampel_filter, 0, amp_matrix)   # (N, S)
    amp_smooth   = np.apply_along_axis(moving_average, 0, amp_filtered)  # (N, S)

    # Per-frame mean amplitude time series
    frame_means = amp_smooth.mean(axis=1)  # (N,)

    # ── RSSI features ─────────────────────────────────────────────────────────
    valid_rssi = rssi_arr[rssi_arr != 0]
    rssi_mean = float(np.mean(valid_rssi)) if len(valid_rssi) > 0 else 0.0
    rssi_std  = float(np.std(valid_rssi))  if len(valid_rssi) > 0 else 0.0

    # ── Amplitude features ────────────────────────────────────────────────────
    amp_mean     = float(np.mean(amp_smooth))
    amp_std_time = float(np.std(frame_means))   # temporal variation of per-frame mean

    # ── Subcarrier spatial features ───────────────────────────────────────────
    subcarrier_var_mean = float(np.mean(np.var(amp_smooth, axis=1)))
    subcarrier_std_mean = float(np.mean(np.std(amp_smooth, axis=1)))

    # ── Temporal difference features ──────────────────────────────────────────
    diffs = np.diff(frame_means)
    temporal_diff_mean_abs = float(np.mean(np.abs(diffs)))
    temporal_diff_std      = float(np.std(diffs))

    # ── Variance (window_var = amp_std_time²) ────────────────────────────────
    signal    = frame_means - frame_means.mean()
    window_var = float(np.var(signal))

    # spectral_total_power == window_var by Parseval's theorem (demeaned signal)
    spectral_total_power = window_var

    # ── FFT spectral features ─────────────────────────────────────────────────
    fft_vals  = np.fft.rfft(signal, n=FFT_N)
    fft_power = np.abs(fft_vals) ** 2
    freqs     = np.fft.rfftfreq(FFT_N)  # normalized [0, 0.5]

    pos_mask  = freqs > 0
    total_pos = float(np.sum(fft_power[pos_mask]))
    if total_pos == 0:
        total_pos = 1.0

    low_mask = (freqs > 0) & (freqs <= LOW_CUTOFF)
    mid_mask = (freqs > LOW_CUTOFF) & (freqs <= MID_CUTOFF)

    low_band_ratio = float(np.sum(fft_power[low_mask])) / total_pos
    mid_band_ratio = float(np.sum(fft_power[mid_mask])) / total_pos

    dom_idx_in_pos   = int(np.argmax(fft_power[pos_mask]))
    dominant_freq_idx = float(freqs[pos_mask][dom_idx_in_pos])

    # ── PCA (SVD): dominant subcarrier direction for correlation analysis ──────
    amp_centered = amp_smooth - amp_smooth.mean(axis=0)
    try:
        _, _, Vt = np.linalg.svd(amp_centered, full_matrices=False)
        pc1_direction = Vt[0]  # principal subcarrier weights (unused in output but useful for future)
    except np.linalg.LinAlgError:
        pc1_direction = None  # noqa: F841 (kept for future use)

    # ── Subcarrier correlation ────────────────────────────────────────────────
    if min_subs > 1:
        corr_matrix  = np.corrcoef(amp_smooth.T)  # (S, S)
        upper_mask   = np.triu(np.ones_like(corr_matrix, dtype=bool), k=1)
        corr_mean_abs = float(np.mean(np.abs(corr_matrix[upper_mask])))
    else:
        corr_mean_abs = 0.0

    return [
        label, "RX1", start,
        rssi_mean, rssi_std,
        amp_mean, amp_std_time,
        subcarrier_var_mean, subcarrier_std_mean,
        temporal_diff_mean_abs, temporal_diff_std,
        window_var, spectral_total_power,
        low_band_ratio, mid_band_ratio,
        dominant_freq_idx, corr_mean_abs,
    ]


# ── Collection loop ──────────────────────────────────────────────────────────

async def collect(label: str, csv_writer):
    loop = asyncio.get_event_loop()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((UDP_IP, UDP_PORT))
    sock.setblocking(False)

    print(f"[FEATURE COLLECTOR] label={label}  port={UDP_PORT}", flush=True)
    print(f"[FEATURE COLLECTOR] window={WINDOW_SIZE} frames | FFT_N={FFT_N}", flush=True)
    print("[FEATURE COLLECTOR] Ctrl+C to stop\n", flush=True)

    frame_buf   = []
    rssi_buf    = []
    total_frames = 0
    window_count = 0

    while True:
        try:
            data, _ = await loop.sock_recvfrom(sock, 65535)
            raw_str = data.decode("utf-8", errors="ignore").strip()
            if not raw_str:
                continue

            parsed = parse_csi(raw_str)
            if parsed is None:
                continue

            frame_buf.append(parsed["amplitudes"])
            rssi_buf.append(parsed["rssi"] if parsed["rssi"] is not None else 0)
            total_frames += 1

            print(f"  [{total_frames}] rssi={parsed['rssi']}  subs={len(parsed['amplitudes'])}", flush=True)

            if len(frame_buf) >= WINDOW_SIZE:
                start_idx = window_count * WINDOW_SIZE
                row = extract_features(frame_buf, rssi_buf, start_idx, label)
                csv_writer.writerow(row)
                window_count += 1
                print(
                    f"[WIN {window_count}] start={start_idx} | "
                    f"amp_mean={row[5]:.3f} window_var={row[11]:.4f} dom_f={row[15]:.4f}",
                    flush=True,
                )
                frame_buf.clear()
                rssi_buf.clear()

        except Exception as e:
            import traceback
            print(f"[ERROR] {e}", flush=True)
            traceback.print_exc()
            await asyncio.sleep(1)


# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--label",
        required=True,
        choices=["occupied", "unoccupied", "fall"],
        help="수집 레이블: occupied / unoccupied / fall",
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
