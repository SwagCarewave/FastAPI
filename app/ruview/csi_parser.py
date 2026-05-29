import re
import math


def parse_csi(raw: str) -> dict | None:
    match = re.search(r'\[([^\]]+)\]', raw)
    if not match:
        return None

    try:
        nums = list(map(int, match.group(1).split()))
    except ValueError:
        return None

    if len(nums) < 4:
        return None

    # ESP32 CSI: [imag0 real0 imag1 real1 ...]
    amplitudes = []
    for i in range(0, len(nums) - 1, 2):
        imag, real = nums[i], nums[i + 1]
        amp = math.sqrt(real ** 2 + imag ** 2)
        if amp > 1.0:  # 0 또는 guard subcarrier 제외
            amplitudes.append(amp)

    if not amplitudes:
        return None

    parts = raw.split(',')
    try:
        rssi = int(parts[3])
    except (IndexError, ValueError):
        rssi = None

    return {"amplitudes": amplitudes, "rssi": rssi}
