from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np


MARGIN = 10
FONT_SIZE = 1
FONT_THICKNESS = 1
HANDEDNESS_TEXT_COLOR = (88, 205, 54)
WINDOW_TITLE = "MediaPipe Hand Detection"
DEFAULT_MODEL_PATH = Path(__file__).with_name("hand_landmarker.task")
INDEX_FINGER_TIP = 8

BaseOptions = mp.tasks.BaseOptions
VisionRunningMode = mp.tasks.vision.RunningMode
HandLandmarker = mp.tasks.vision.HandLandmarker
HandLandmarkerOptions = mp.tasks.vision.HandLandmarkerOptions
HandLandmarksConnections = mp.tasks.vision.HandLandmarksConnections
mp_drawing = mp.tasks.vision.drawing_utils
mp_drawing_styles = mp.tasks.vision.drawing_styles


@dataclass(slots=True)
class HandDetectionConfig:
    model_path: Path = DEFAULT_MODEL_PATH
    camera_index: int = 0
    mirror_display: bool = True
    mirror_input: bool = True
    max_num_hands: int = 2
    min_detection_confidence: float = 0.5
    min_presence_confidence: float = 0.5
    min_tracking_confidence: float = 0.5


@dataclass(slots=True)
class HandObservation:
    label: str
    score: float
    wrist_x: float
    wrist_y: float
    index_tip_x: float
    index_tip_y: float


def draw_landmarks_on_image(rgb_image: np.ndarray, detection_result) -> np.ndarray:
    hand_landmarks_list = detection_result.hand_landmarks
    handedness_list = detection_result.handedness
    annotated_image = np.copy(rgb_image)

    for idx in range(len(hand_landmarks_list)):
        hand_landmarks = hand_landmarks_list[idx]
        handedness = handedness_list[idx]

        mp_drawing.draw_landmarks(
            annotated_image,
            hand_landmarks,
            HandLandmarksConnections.HAND_CONNECTIONS,
            mp_drawing_styles.get_default_hand_landmarks_style(),
            mp_drawing_styles.get_default_hand_connections_style(),
        )

        height, width, _ = annotated_image.shape
        x_coordinates = [landmark.x for landmark in hand_landmarks]
        y_coordinates = [landmark.y for landmark in hand_landmarks]
        text_x = int(min(x_coordinates) * width)
        text_y = max(int(min(y_coordinates) * height) - MARGIN, MARGIN)

        cv2.putText(
            annotated_image,
            f"{handedness[0].category_name} {handedness[0].score:.2f}",
            (text_x, text_y),
            cv2.FONT_HERSHEY_DUPLEX,
            FONT_SIZE,
            HANDEDNESS_TEXT_COLOR,
            FONT_THICKNESS,
            cv2.LINE_AA,
        )

    return annotated_image


def create_detector(config: HandDetectionConfig) -> HandLandmarker:
    model_path = config.model_path.resolve()
    if not model_path.exists():
        raise FileNotFoundError(
            "Hand landmarker model file not found: "
            f"{model_path}\n"
            "Please place `hand_landmarker.task` in the `vision` folder, "
            "or pass `--model <path>`."
        )

    options = HandLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(model_path)),
        running_mode=VisionRunningMode.VIDEO,
        num_hands=config.max_num_hands,
        min_hand_detection_confidence=config.min_detection_confidence,
        min_hand_presence_confidence=config.min_presence_confidence,
        min_tracking_confidence=config.min_tracking_confidence,
    )
    return HandLandmarker.create_from_options(options)


def extract_hand_observations(detection_result) -> list[HandObservation]:
    observations: list[HandObservation] = []
    for hand_landmarks, handedness in zip(
        detection_result.hand_landmarks,
        detection_result.handedness,
    ):
        wrist = hand_landmarks[0]
        index_tip = hand_landmarks[INDEX_FINGER_TIP]
        observations.append(
            HandObservation(
                label=handedness[0].category_name,
                score=handedness[0].score,
                wrist_x=wrist.x,
                wrist_y=wrist.y,
                index_tip_x=index_tip.x,
                index_tip_y=index_tip.y,
            )
        )
    return observations


class HandTracker:
    def __init__(self, config: HandDetectionConfig) -> None:
        self.config = config
        self.camera = cv2.VideoCapture(config.camera_index)
        if not self.camera.isOpened():
            raise RuntimeError(
                f"Could not open camera index {config.camera_index}. "
                "Check whether the webcam is available or already in use."
            )
        self.detector = create_detector(config)

    def poll(self) -> tuple[np.ndarray | None, object, list[HandObservation]]:
        success, frame = self.camera.read()
        if not success:
            return None, None, []

        display_frame = cv2.flip(frame, 1) if self.config.mirror_display else frame.copy()
        detection_frame = cv2.flip(frame, 1) if self.config.mirror_input else frame
        rgb_detection_frame = cv2.cvtColor(detection_frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_detection_frame)
        timestamp_ms = int(time.monotonic() * 1000)
        detection_result = self.detector.detect_for_video(mp_image, timestamp_ms)
        observations = extract_hand_observations(detection_result)
        rgb_display_frame = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)
        return rgb_display_frame, detection_result, observations

    def close(self) -> None:
        self.detector.close()
        self.camera.release()


def run_hand_detection(config: HandDetectionConfig) -> int:
    tracker = HandTracker(config)

    try:
        while True:
            rgb_frame, detection_result, _ = tracker.poll()
            if rgb_frame is None or detection_result is None:
                continue

            annotated_image = draw_landmarks_on_image(rgb_frame, detection_result)
            cv2.imshow(WINDOW_TITLE, cv2.cvtColor(annotated_image, cv2.COLOR_RGB2BGR))
            key = cv2.waitKey(1) & 0xFF
            if key in (27, ord("q")):
                break
    finally:
        tracker.close()
        cv2.destroyAllWindows()

    return 0


def parse_args() -> HandDetectionConfig:
    parser = argparse.ArgumentParser(description="Run MediaPipe hand detection with a webcam.")
    parser.add_argument(
        "--model",
        type=Path,
        default=DEFAULT_MODEL_PATH,
        help="Path to `hand_landmarker.task`. Default is `vision/hand_landmarker.task`.",
    )
    parser.add_argument("--camera", type=int, default=0, help="Webcam index. Default is 0.")
    parser.add_argument(
        "--no-mirror-input",
        action="store_true",
        help="Do not mirror the frame before hand detection. Use this if left/right is reversed.",
    )
    parser.add_argument(
        "--no-mirror-display",
        action="store_true",
        help="Do not mirror the preview window.",
    )
    parser.add_argument("--max-hands", type=int, default=2, help="Maximum number of hands to detect.")
    parser.add_argument(
        "--min-detection-confidence",
        type=float,
        default=0.5,
        help="Minimum confidence for the palm detector.",
    )
    parser.add_argument(
        "--min-presence-confidence",
        type=float,
        default=0.5,
        help="Minimum confidence for the hand-presence score.",
    )
    parser.add_argument(
        "--min-tracking-confidence",
        type=float,
        default=0.5,
        help="Minimum confidence for landmark tracking.",
    )
    args = parser.parse_args()
    return HandDetectionConfig(
        model_path=args.model,
        camera_index=args.camera,
        mirror_display=not args.no_mirror_display,
        mirror_input=not args.no_mirror_input,
        max_num_hands=args.max_hands,
        min_detection_confidence=args.min_detection_confidence,
        min_presence_confidence=args.min_presence_confidence,
        min_tracking_confidence=args.min_tracking_confidence,
    )


def main() -> int:
    return run_hand_detection(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
