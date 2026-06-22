"""
model.pkl 로드 및 실시간 재실/비재실 예측.
feature_extractor.extract_features() 반환값을 입력으로 받음.
"""
import os

_MODEL_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'ml', 'model.pkl')
_FEAT_PATH  = os.path.join(os.path.dirname(__file__), '..', '..', 'ml', 'feature_cols.pkl')


class MLPredictor:
    def __init__(self):
        self.model        = None
        self.feature_cols = None
        self._load()

    def _load(self):
        try:
            import joblib
            if os.path.exists(_MODEL_PATH) and os.path.exists(_FEAT_PATH):
                self.model        = joblib.load(_MODEL_PATH)
                self.feature_cols = joblib.load(_FEAT_PATH)
                print("[ML] model.pkl 로드 완료", flush=True)
            else:
                print("[ML] model.pkl 없음 — 임계값 방식으로 폴백", flush=True)
        except Exception as e:
            print(f"[ML] 로드 실패: {e}", flush=True)

    @property
    def ready(self) -> bool:
        return self.model is not None and self.feature_cols is not None

    def predict(self, feature_dict: dict, rx: str) -> tuple[bool, float]:
        """
        feature_dict : extract_features() 반환 dict
        rx           : "RX1" | "RX2" | "RX3"

        Returns (is_occupied, confidence 0~1)
        """
        if not self.ready:
            return False, 0.0

        import pandas as pd

        row = dict(feature_dict)

        # rx One-Hot 컬럼 세팅
        for col in [c for c in self.feature_cols if c.startswith('rx_')]:
            row[col] = 1.0 if col == f"rx_{rx}" else 0.0

        df = pd.DataFrame([row])
        for col in self.feature_cols:
            if col not in df.columns:
                df[col] = 0.0
        df = df[self.feature_cols]

        is_occupied = bool(self.model.predict(df)[0])
        try:
            proba      = self.model.predict_proba(df)[0]
            confidence = float(proba[1] if is_occupied else proba[0])
        except AttributeError:
            confidence = 1.0

        return is_occupied, confidence


predictor = MLPredictor()
