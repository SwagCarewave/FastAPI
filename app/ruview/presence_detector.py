from collections import deque
from typing import Optional
import statistics

WINDOW_SIZE = 30

AVG_VAR_THRESHOLD = 22.0   # >= 22 → 공실, < 22 → 재실
WINDOW_STD_THRESHOLD = 1.5
FRAME_DIFF_THRESHOLD = 0.7


class PresenceDetector:
    def __init__(self):
        self._window: deque[list[float]] = deque(maxlen=WINDOW_SIZE)
        self._var_window: deque[float] = deque(maxlen=WINDOW_SIZE)
        self._prev_frame: Optional[list[float]] = None

    def update(self, amplitudes: list[float]) -> tuple[bool, float, float, float]:
        # frame_diff: 직전 프레임과의 amplitude 평균 절대 차이
        if self._prev_frame is not None:
            n = min(len(amplitudes), len(self._prev_frame))
            diffs = [abs(amplitudes[i] - self._prev_frame[i]) for i in range(n)]
            frame_diff = sum(diffs) / len(diffs) if diffs else 0.0
        else:
            frame_diff = 0.0
        self._prev_frame = amplitudes

        self._window.append(amplitudes)

        if len(self._window) < 5:
            return False, 0.0, 0.0, frame_diff

        n_carriers = min(len(frame) for frame in self._window)
        variances = []
        for i in range(n_carriers):
            vals = [self._window[j][i] for j in range(len(self._window)) if i < len(self._window[j])]
            if len(vals) >= 2:
                variances.append(statistics.variance(vals))

        if not variances:
            return False, 0.0, 0.0, frame_diff

        avg_var = sum(variances) / len(variances)
        self._var_window.append(avg_var)
        window_std = statistics.stdev(self._var_window) if len(self._var_window) >= 2 else 0.0

        is_present = avg_var < AVG_VAR_THRESHOLD
        return is_present, avg_var, window_std, frame_diff


detector = PresenceDetector()
