import torch
import torch.nn as nn
import pandas as pd
import numpy as np
from torch.utils.data import Dataset, DataLoader
import sys
import os

# 입력 특성값 컬럼
CSI_FEATURES = [
    "variance",
    "motion_band_power",
    "breathing_band_power",
    "dominant_freq_hz",
    "change_points",
    "spectral_power",
]

# 출력 키포인트 (17개 COCO 기준 주요 키포인트)
KEYPOINT_COLS = []
for name in [
    "nose", "left_eye", "right_eye", "left_ear", "right_ear",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_hip", "right_hip",
    "left_knee", "right_knee", "left_ankle", "right_ankle"
]:
    KEYPOINT_COLS.append(f"{name}_x")
    KEYPOINT_COLS.append(f"{name}_y")

INPUT_SIZE = len(CSI_FEATURES)   # 6
OUTPUT_SIZE = len(KEYPOINT_COLS)  # 34 (17개 x,y)
SEQUENCE_LEN = 20  # 20프레임 시퀀스로 예측


class CSIDataset(Dataset):
    def __init__(self, csv_path: str):
        df = pd.read_csv(csv_path)

        # 키포인트 컬럼 없는 거 필터
        available_kp = [c for c in KEYPOINT_COLS if c in df.columns]
        df = df.dropna(subset=available_kp)

        self.X = df[CSI_FEATURES].values.astype(np.float32)
        self.y = df[available_kp].values.astype(np.float32)

        # 정규화
        self.X_mean = self.X.mean(axis=0)
        self.X_std = self.X.std(axis=0) + 1e-8
        self.X = (self.X - self.X_mean) / self.X_std

        print(f"데이터셋 크기: {len(self.X)} 프레임")

    def __len__(self):
        return len(self.X) - SEQUENCE_LEN

    def __getitem__(self, idx):
        x = self.X[idx:idx + SEQUENCE_LEN]  # (seq, features)
        y = self.y[idx + SEQUENCE_LEN]       # 마지막 프레임 키포인트
        return torch.tensor(x), torch.tensor(y)


class KeypointCNN(nn.Module):
    def __init__(self):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv1d(INPUT_SIZE, 64, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.Conv1d(64, 128, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.Conv1d(128, 64, kernel_size=3, padding=1),
            nn.ReLU(),
        )
        self.fc = nn.Sequential(
            nn.Flatten(),
            nn.Linear(64 * SEQUENCE_LEN, 256),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(256, OUTPUT_SIZE),
            nn.Sigmoid()  # x,y를 0~1 범위로
        )

    def forward(self, x):
        # x: (batch, seq, features) → (batch, features, seq)
        x = x.permute(0, 2, 1)
        x = self.conv(x)
        x = self.fc(x)
        return x


def train(csv_path: str, model_path: str = "keypoint_model.pt", epochs: int = 50):
    dataset = CSIDataset(csv_path)
    loader = DataLoader(dataset, batch_size=32, shuffle=True)

    model = KeypointCNN()
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    criterion = nn.MSELoss()

    print(f"학습 시작 (epochs={epochs})")
    for epoch in range(epochs):
        model.train()
        total_loss = 0
        for X_batch, y_batch in loader:
            optimizer.zero_grad()
            pred = model(X_batch)
            loss = criterion(pred, y_batch)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()

        avg_loss = total_loss / len(loader)
        if (epoch + 1) % 10 == 0:
            print(f"Epoch {epoch+1}/{epochs} | Loss: {avg_loss:.4f}")

    torch.save({
        "model_state": model.state_dict(),
        "X_mean": dataset.X_mean,
        "X_std": dataset.X_std,
    }, model_path)
    print(f"모델 저장됨: {model_path}")


def predict(features: dict, model_path: str = "keypoint_model.pt", history: list = None):
    """
    실시간 추론
    features: {variance, motion_band_power, ...}
    history: 이전 프레임 특성값 리스트 (최근 SEQUENCE_LEN개)
    """
    checkpoint = torch.load(model_path, map_location="cpu")
    model = KeypointCNN()
    model.load_state_dict(checkpoint["model_state"])
    model.eval()

    X_mean = checkpoint["X_mean"]
    X_std = checkpoint["X_std"]

    if history is None or len(history) < SEQUENCE_LEN:
        return None

    seq = np.array([[h[f] for f in CSI_FEATURES] for h in history[-SEQUENCE_LEN:]], dtype=np.float32)
    seq = (seq - X_mean) / X_std
    seq_tensor = torch.tensor(seq).unsqueeze(0)  # (1, seq, features)

    with torch.no_grad():
        pred = model(seq_tensor).squeeze(0).numpy()

    result = {}
    for i, col in enumerate(KEYPOINT_COLS):
        result[col] = float(pred[i])

    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법: python keypoint_model.py <동기화된CSV> [모델저장경로] [에폭수]")
        sys.exit(1)

    csv_path = sys.argv[1]
    model_path = sys.argv[2] if len(sys.argv) > 2 else "keypoint_model.pt"
    epochs = int(sys.argv[3]) if len(sys.argv) > 3 else 50

    train(csv_path, model_path, epochs)
