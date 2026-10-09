from ultralytics import YOLO


class ObjectDetector:
    """
    Wrapper around YOLOv8 (COCO-pretrained) for detecting prohibited objects
    during an exam — currently focused on mobile phones.

    NOTE on Smart Watches: "smart watch" is NOT one of the 80 standard COCO
    classes, so it can't be detected with this generic model. Detecting watches
    will require a custom-trained model with a dedicated dataset — a separate,
    later phase of the project (see project architecture notes).
    """

    # COCO class IDs relevant to exam proctoring (from the 80 standard COCO classes)
    COCO_CLASS_IDS = {
        "cell phone": 67,
    }

    def __init__(self, model_path: str = "yolov8n.pt", confidence_threshold: float = 0.4):
        """
        confidence_threshold is slightly lower than PersonDetector's (0.5) because
        phones are small objects and often partially occluded by hands — a stricter
        threshold risks missing real detections.
        """
        self.model = YOLO(model_path)
        self.confidence_threshold = confidence_threshold
        self.target_class_ids = set(self.COCO_CLASS_IDS.values())

    def detect(self, frame):
        """
        Run detection on a single BGR frame, filtering for target object classes only.

        Returns a list of dicts, one per detected object:
            {
                "label": str,              # e.g. "cell phone"
                "bbox": (x1, y1, x2, y2),  # pixel coordinates
                "confidence": float,
            }
        """
        results = self.model(frame, verbose=False)[0]

        # Reverse lookup: class_id -> label name
        id_to_label = {v: k for k, v in self.COCO_CLASS_IDS.items()}

        detected_objects = []
        for box in results.boxes:
            class_id = int(box.cls[0])
            confidence = float(box.conf[0])

            if class_id in self.target_class_ids and confidence >= self.confidence_threshold:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                detected_objects.append({
                    "label": id_to_label[class_id],
                    "bbox": (x1, y1, x2, y2),
                    "confidence": confidence,
                })

        return detected_objects