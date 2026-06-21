"""YOLO Detector — phone and multiple person detection.

Uses YOLOv8-nano (6MB) running at 5fps on the webcam feed.
Both phone and person detection run in the same YOLO pass — no extra cost.

Rules (from implementation plan):
- Phone: confidence > 0.6, 2 consecutive detections → PHONE_DETECTED
- Person: count > 1, 3 consecutive frames → MULTIPLE_PERSONS
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import structlog

logger = structlog.get_logger()

# Default model path (relative to this file)
_MODEL_DIR = os.path.join(os.path.dirname(__file__), "models")
_YOLO_MODEL_PATH = os.path.join(_MODEL_DIR, "yolov8n.pt")

# COCO class IDs
PERSON_CLASS_ID = 0
PHONE_CLASS_ID = 67  # "cell phone" in COCO


@dataclass
class YoloResult:
    """Result from YOLO detection pass."""
    phone_detected: bool = False
    phone_confidence: float = 0.0
    phone_bbox: Optional[list[float]] = None
    person_count: int = 0
    person_bboxes: list[list[float]] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)


class YoloDetector:
    """YOLOv8-nano based object detector for phones and persons.

    Runs in the same inference pass for both detections.
    Uses consecutive frame counting to avoid false positives.
    """

    def __init__(
        self,
        model_path: str = _YOLO_MODEL_PATH,
        confidence_threshold: float = 0.6,
        phone_consecutive_threshold: int = 2,
        person_consecutive_threshold: int = 3,
        iou_threshold: float = 0.5,
    ):
        self.confidence_threshold = confidence_threshold
        self.phone_consecutive_threshold = phone_consecutive_threshold
        self.person_consecutive_threshold = person_consecutive_threshold
        self.iou_threshold = iou_threshold

        # Lazy-load YOLO model
        self._model = None
        self._model_path = model_path

        # Consecutive detection counters
        self._phone_streak = 0
        self._person_streak = 0

    def _load_model(self):
        """Lazy-load the YOLO model on first use."""
        if self._model is None:
            from ultralytics import YOLO
            self._model = YOLO(self._model_path)
            logger.info("yolo_model_loaded", path=self._model_path)

    def process(self, frame: np.ndarray) -> YoloResult:
        """Run YOLO inference on a frame.

        Args:
            frame: BGR image from webcam.

        Returns:
            YoloResult with phone/person detections and flags.
        """
        self._load_model()
        result = YoloResult()

        # Run inference
        detections = self._model(frame, verbose=False, conf=self.confidence_threshold)

        if not detections or len(detections) == 0:
            self._phone_streak = 0
            self._person_streak = 0
            return result

        boxes = detections[0].boxes
        if boxes is None or len(boxes) == 0:
            self._phone_streak = 0
            self._person_streak = 0
            return result

        classes = boxes.cls.cpu().numpy().astype(int)
        confidences = boxes.conf.cpu().numpy()
        xyxy = boxes.xyxy.cpu().numpy()

        # Debug: log all detections for diagnostics
        if len(classes) > 0:
            det_summary = {}
            for cls_id, conf in zip(classes, confidences):
                name = self._model.names.get(cls_id, f"class_{cls_id}")
                if name not in det_summary or conf > det_summary[name]:
                    det_summary[name] = float(conf)
            logger.debug("yolo_detections", detections=det_summary)

        # Phone detection
        phone_mask = classes == PHONE_CLASS_ID
        if phone_mask.any():
            best_idx = confidences[phone_mask].argmax()
            phone_indices = np.where(phone_mask)[0]
            result.phone_detected = True
            result.phone_confidence = float(confidences[phone_indices[best_idx]])
            result.phone_bbox = xyxy[phone_indices[best_idx]].tolist()
            self._phone_streak += 1
        else:
            self._phone_streak = 0

        # Person detection with IoU deduplication
        person_mask = classes == PERSON_CLASS_ID
        if person_mask.any():
            person_boxes = xyxy[person_mask]
            person_confs = confidences[person_mask]
            # NMS deduplication
            deduped = self._nms(person_boxes, person_confs)
            result.person_count = len(deduped)
            result.person_bboxes = [b.tolist() for b in deduped]
        else:
            result.person_count = 0

        # Consecutive frame logic for flags
        if self._phone_streak >= self.phone_consecutive_threshold:
            result.flags.append("PHONE_DETECTED")
            logger.warning(
                "phone_detected",
                confidence=result.phone_confidence,
                streak=self._phone_streak,
            )

        if result.person_count > 1:
            self._person_streak += 1
        else:
            self._person_streak = 0

        if self._person_streak >= self.person_consecutive_threshold:
            result.flags.append("MULTIPLE_PERSONS")
            logger.warning(
                "multiple_persons",
                count=result.person_count,
                streak=self._person_streak,
            )

        return result

    def _nms(
        self, boxes: np.ndarray, scores: np.ndarray
    ) -> list[np.ndarray]:
        """Non-maximum suppression for person bounding boxes."""
        if len(boxes) == 0:
            return []

        # Sort by confidence
        order = scores.argsort()[::-1]
        keep = []

        while len(order) > 0:
            i = order[0]
            keep.append(boxes[i])

            if len(order) == 1:
                break

            # Compute IoU with remaining boxes
            rest = order[1:]
            xx1 = np.maximum(boxes[i, 0], boxes[rest, 0])
            yy1 = np.maximum(boxes[i, 1], boxes[rest, 1])
            xx2 = np.minimum(boxes[i, 2], boxes[rest, 2])
            yy2 = np.minimum(boxes[i, 3], boxes[rest, 3])

            w = np.maximum(0, xx2 - xx1)
            h = np.maximum(0, yy2 - yy1)
            inter = w * h

            area_i = (boxes[i, 2] - boxes[i, 0]) * (boxes[i, 3] - boxes[i, 1])
            area_rest = (boxes[rest, 2] - boxes[rest, 0]) * (boxes[rest, 3] - boxes[rest, 1])
            union = area_i + area_rest - inter

            iou = inter / (union + 1e-6)
            order = rest[iou < self.iou_threshold]

        return keep

    def reset_streaks(self):
        """Reset consecutive detection counters (e.g., on session start)."""
        self._phone_streak = 0
        self._person_streak = 0
