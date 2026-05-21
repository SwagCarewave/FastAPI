import cv2
import mediapipe as mp
import csv
import sys
import os

mp_pose = mp.solutions.pose

KEYPOINT_NAMES = [
    "nose", "left_eye_inner", "left_eye", "left_eye_outer",
    "right_eye_inner", "right_eye", "right_eye_outer",
    "left_ear", "right_ear", "mouth_left", "mouth_right",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_pinky", "right_pinky",
    "left_index", "right_index", "left_thumb", "right_thumb",
    "left_hip", "right_hip", "left_knee", "right_knee",
    "left_ankle", "right_ankle", "left_heel", "right_heel",
    "left_foot_index", "right_foot_index"
]

FIELDNAMES = ["timestamp"] + [f"{name}_x" for name in KEYPOINT_NAMES] + [f"{name}_y" for name in KEYPOINT_NAMES]


def extract(video_path: str, output_csv: str, start_offset: float = 0.0):
    """
    video_path: 영상 파일 경로
    output_csv: 저장할 CSV 경로
    start_offset: 영상 시작 시간 오프셋 (초) - CSI 수집 시작과 동기화용
    """
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"영상 FPS: {fps}, 총 프레임: {total_frames}")

    with open(output_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()

        with mp_pose.Pose(
            static_image_mode=False,
            model_complexity=1,
            smooth_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        ) as pose:
            frame_idx = 0
            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break

                timestamp = start_offset + frame_idx / fps
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                result = pose.process(rgb)

                row = {"timestamp": timestamp}

                if result.pose_landmarks:
                    for i, name in enumerate(KEYPOINT_NAMES):
                        lm = result.pose_landmarks.landmark[i]
                        row[f"{name}_x"] = lm.x
                        row[f"{name}_y"] = lm.y
                else:
                    for name in KEYPOINT_NAMES:
                        row[f"{name}_x"] = None
                        row[f"{name}_y"] = None

                writer.writerow(row)
                frame_idx += 1

                if frame_idx % 100 == 0:
                    print(f"처리 중: {frame_idx}/{total_frames} 프레임")

    cap.release()
    print(f"완료. {output_csv} 저장됨")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("사용법: python mediapipe_extract.py <영상파일> <출력CSV> [시작오프셋(초)]")
        print("예시: python mediapipe_extract.py video.mp4 keypoints.csv 0.0")
        sys.exit(1)

    video_path = sys.argv[1]
    output_csv = sys.argv[2]
    start_offset = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0

    extract(video_path, output_csv, start_offset)
