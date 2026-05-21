import pandas as pd
import numpy as np
import sys


def sync(csi_csv: str, keypoint_csv: str, output_csv: str, tolerance: float = 0.1):
    """
    CSI CSV와 키포인트 CSV를 타임스탬프 기준으로 동기화
    tolerance: 매칭 허용 오차 (초)
    """
    csi_df = pd.read_csv(csi_csv)
    kp_df = pd.read_csv(keypoint_csv)

    print(f"CSI 프레임 수: {len(csi_df)}")
    print(f"키포인트 프레임 수: {len(kp_df)}")

    merged_rows = []

    for _, csi_row in csi_df.iterrows():
        csi_ts = csi_row["timestamp"]
        diff = np.abs(kp_df["timestamp"] - csi_ts)
        min_idx = diff.idxmin()

        if diff[min_idx] <= tolerance:
            kp_row = kp_df.loc[min_idx]
            merged = {**csi_row.to_dict(), **{k: v for k, v in kp_row.to_dict().items() if k != "timestamp"}}
            merged_rows.append(merged)

    result_df = pd.DataFrame(merged_rows)
    result_df = result_df.dropna()
    result_df.to_csv(output_csv, index=False)
    print(f"동기화 완료. {len(result_df)}개 쌍 저장됨 → {output_csv}")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("사용법: python sync_data.py <CSI CSV> <키포인트 CSV> <출력 CSV>")
        sys.exit(1)

    sync(sys.argv[1], sys.argv[2], sys.argv[3])
