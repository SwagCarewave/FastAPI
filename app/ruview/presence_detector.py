from collections import deque
import statistics

WINDOW_SIZE = 30
VARIANCE_THRESHOLD = 2.0


class PresenceDetector:
    def __init__(self):
        self._window: deque[list[float]] = deque(maxlen=WINDOW_SIZE)
        self._var_window: deque[float] = deque(maxlen=WINDOW_SIZE)

    def update(self, amplitudes: list[float]) -> tuple[bool, float, float]:
        self._window.append(amplitudes)

        if len(self._window) < 5:
            return False, 0.0, 0.0

        n_carriers = min(len(frame) for frame in self._window)
        variances = []
        for i in range(n_carriers):
            vals = [self._window[j][i] for j in range(len(self._window)) if i < len(self._window[j])]
            if len(vals) >= 2:
                variances.append(statistics.variance(vals))

        if not variances:
            return False, 0.0, 0.0

        avg_var = sum(variances) / len(variances)
        self._var_window.append(avg_var)

        window_std = statistics.stdev(self._var_window) if len(self._var_window) >= 2 else 0.0

        return avg_var > VARIANCE_THRESHOLD, avg_var, window_std


detector = PresenceDetector()
