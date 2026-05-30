"""
CSI 전처리 + 특징 추출 공통 모듈.
collect_raw.py(데이터 수집)와 udp_receiver.py(실시간 추론) 공용.
"""
import math
import re

import numpy as np

WINDOW_SIZE     = 100
FFT_N           = 128
HAMPEL_HALF_WIN = 5
HAMPEL_SIGMA    = 3.0
MA_WIN          = 5
LOW_CUTOFF      = 0.1
MID_CUTOFF      = 0.4

FEATURE_NAMES = [
    "rssi_mean", "rssi_std",
    "amp_mean", "amp_std_time",
    "subcarrier_var_mean", "subcarrier_std_mean",
    "temporal_diff_mean_abs", "temporal_diff_std",
    "window_var", "spectral_total_power",
    "low_band_ratio", "mid_band_ratio",
    "dominant_freq_idx", "corr_mean_abs",
    "spectral_entropy", "peak_to_peak", "skewness", "kurtosis",
]

CSV_HEADER = ["label", "rx", "start"] + FEATURE_NAMES


# ── Parsing ───────────────────────────────────────────────────────────────────

def parse_csi(raw: str) -> dict | None:
    """ESP32 CSI UDP 패킷 → amplitudes + RSSI + rx 레이블."""
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
        if amp > 0:
            amplitudes.append(amp)

    if not amplitudes:
        return None

    parts = raw.split(',')
    try:
        rssi = int(parts[3])
    except (IndexError, ValueError):
        rssi = None

    rx = parts[1] if len(parts) > 1 else "RX1"

    return {"amplitudes": amplitudes, "rssi": rssi, "rx": rx}


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

def extract_features(frames: list, rssi_list: list) -> dict:
    """
    frames   : list of amplitude arrays (per frame)
    rssi_list: RSSI per frame

    Returns dict matching FEATURE_NAMES keys.
    """
    min_subs   = min(len(f) for f in frames)
    amp_matrix = np.array([f[:min_subs] for f in frames], dtype=float)
    rssi_arr   = np.array(rssi_list, dtype=float)

    amp_filtered = np.apply_along_axis(hampel_filter, 0, amp_matrix)
    amp_smooth   = np.apply_along_axis(moving_average, 0, amp_filtered)
    frame_means  = amp_smooth.mean(axis=1)

    valid_rssi = rssi_arr[rssi_arr != 0]
    rssi_mean  = float(np.mean(valid_rssi)) if len(valid_rssi) > 0 else 0.0
    rssi_std   = float(np.std(valid_rssi))  if len(valid_rssi) > 0 else 0.0

    amp_mean     = float(np.mean(amp_smooth))
    amp_std_time = float(np.std(frame_means))

    subcarrier_var_mean = float(np.mean(np.var(amp_smooth, axis=1)))
    subcarrier_std_mean = float(np.mean(np.std(amp_smooth, axis=1)))

    diffs = np.diff(frame_means)
    temporal_diff_mean_abs = float(np.mean(np.abs(diffs)))
    temporal_diff_std      = float(np.std(diffs))

    signal               = frame_means - frame_means.mean()
    window_var           = float(np.var(signal))
    spectral_total_power = window_var

    fft_vals  = np.fft.rfft(signal, n=FFT_N)
    fft_power = np.abs(fft_vals) ** 2
    freqs     = np.fft.rfftfreq(FFT_N)
    pos_mask  = freqs > 0
    total_pos = float(np.sum(fft_power[pos_mask])) or 1.0

    low_band_ratio    = float(np.sum(fft_power[(freqs > 0) & (freqs <= LOW_CUTOFF)])) / total_pos
    mid_band_ratio    = float(np.sum(fft_power[(freqs > LOW_CUTOFF) & (freqs <= MID_CUTOFF)])) / total_pos
    dom_idx           = int(np.argmax(fft_power[pos_mask]))
    dominant_freq_idx = float(freqs[pos_mask][dom_idx])

    try:
        amp_centered = amp_smooth - amp_smooth.mean(axis=0)
        np.linalg.svd(amp_centered, full_matrices=False)
    except np.linalg.LinAlgError:
        pass

    corr_mean_abs = 0.0
    if min_subs > 1:
        corr_matrix   = np.corrcoef(amp_smooth.T)
        upper         = np.triu(np.ones_like(corr_matrix, dtype=bool), k=1)
        corr_mean_abs = float(np.mean(np.abs(corr_matrix[upper])))

    prob             = fft_power[pos_mask] / total_pos
    spectral_entropy = float(-np.sum(prob * np.log2(prob + 1e-12)))
    peak_to_peak     = float(np.max(frame_means) - np.min(frame_means))
    std              = float(np.std(signal)) or 1e-10
    skewness         = float(np.mean(((signal - signal.mean()) / std) ** 3))
    kurtosis         = float(np.mean(((signal - signal.mean()) / std) ** 4) - 3)

    return {
        "rssi_mean": rssi_mean, "rssi_std": rssi_std,
        "amp_mean": amp_mean, "amp_std_time": amp_std_time,
        "subcarrier_var_mean": subcarrier_var_mean, "subcarrier_std_mean": subcarrier_std_mean,
        "temporal_diff_mean_abs": temporal_diff_mean_abs, "temporal_diff_std": temporal_diff_std,
        "window_var": window_var, "spectral_total_power": spectral_total_power,
        "low_band_ratio": low_band_ratio, "mid_band_ratio": mid_band_ratio,
        "dominant_freq_idx": dominant_freq_idx, "corr_mean_abs": corr_mean_abs,
        "spectral_entropy": spectral_entropy, "peak_to_peak": peak_to_peak,
        "skewness": skewness, "kurtosis": kurtosis,
    }
