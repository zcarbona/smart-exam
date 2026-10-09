# Smart Exam Proctoring System — Situation Report (Codebase Audit & Status)

**Project Type:** University Graduation Project — Proof of Concept (PoC)  
**Domain:** Computer Vision & AI-Assisted Automated Exam Proctoring  
**Core Technologies:** Python 3.10+, OpenCV, MediaPipe, Ultralytics YOLOv8, Flask, HTML5/CSS3/JavaScript  
**Date of Audit:** October 2026  

---

## 1. Executive Summary

The **Smart Exam Proctoring System** is an AI-powered, real-time computer vision proof-of-concept designed to assist exam invigilators in detecting suspicious student behavior during in-person exams. The system operates locally from a single camera feed (webcam or Continuity Camera/phone) and feeds analysis into an interactive Flask-based web dashboard.

The project demonstrates high potential for an academic graduation project, incorporating multiple modern computer vision pipelines (object detection, multi-person tracking, pose estimation, facial landmark analysis, and pupil gaze tracking) tied together through a rule-based scoring engine.

However, as a prototype, it contains key architectural strengths alongside specific performance bottlenecks, code duplications, and spatial association bugs that must be addressed before final project defense and live demonstrations.

---

## 2. System Architecture & Module Inventory

The repository is structured into distinct modular components:

```
smart-exam/
├── camera_capture.py       # Camera hardware abstraction & discovery
├── face_detector.py        # MediaPipe Face Detection + solvePnP Head Pose Estimation
├── eye_gaze.py             # MediaPipe Face Mesh Iris Tracking & Gaze Classification
├── person_detector.py      # YOLOv8 Person Detector + MediaPipe Body Pose Estimator
├── boundary_zones.py       # Seat calibration (DeskZoneManager) + spine tilt analyzer
├── object_detector.py      # YOLOv8 prohibited object detector (cell phones)
├── scoring_system.py       # Student record state machine, scoring rules, personal gaze calibration
├── dashboard.py            # Flask server, background detection thread, CentroidTracker, REST API
├── templates/
│   └── index.html          # Responsive single-page proctor dashboard UI
├── requirements.txt        # Pinned dependencies
├── yolov8n.pt              # Pretrained YOLOv8 nano model weights (~6.5 MB)
├── test_*.py               # Component-level and end-to-end integration test scripts
```

### Module Breakdown

| Module | Core Technology | Primary Responsibility | Status |
| :--- | :--- | :--- | :--- |
| **`camera_capture.py`** | OpenCV (`cv2.VideoCapture`) | Manages frame acquisition, auto-exposure, resolution setting (default 1280x720 @ 30 FPS), and iPhone/Continuity Camera index scanning (`list_available_cameras()`). | **Stable** |
| **`face_detector.py`** | MediaPipe Face Detection + Face Mesh + `cv2.solvePnP` | Detects facial bounding boxes and 6 keypoints; uses 6 3D facial landmarks with `solvePnP` and Rodrigues rotation conversion to compute head **Yaw, Pitch, and Roll** in degrees. | **Stable** |
| **`eye_gaze.py`** | MediaPipe Face Mesh (`refine_landmarks=True`) | Tracks iris landmark coordinates (centers 468, 473) relative to inner/outer eye corners (33, 133, 362, 263) and eye lids. Computes horizontal/vertical ratios and classifies directions (*Eyes Left, Right, Up, Down, Center*). | **Functional** (High CPU cost) |
| **`person_detector.py`** | Ultralytics YOLOv8n + MediaPipe Pose | Detects students in frame (COCO class 0). Implements ROI-based cropped pose estimation (`estimate_in_region`) to compute shoulder/hip centers, torso length, and spine tilt angle in degrees. | **Stable** |
| **`boundary_zones.py`** | Vector math / NumPy Euclidean distance | **`DeskZoneManager`**: Calibrates virtual seat boundaries using an initial 30-frame rolling average, assigning normalized safe (1.5x torso) and violation (2.2x torso) radii.<br>**`BoundaryZoneAnalyzer`**: Evaluates individual student spine tilt angles (warning: 15 deg, violation: 25 deg). | **Stable** |
| **`object_detector.py`** | Ultralytics YOLOv8n (confidence 0.4) | Scans for prohibited objects in frame, currently filtered to COCO class 67 (`cell phone`). | **Functional** (Limited classes) |
| **`scoring_system.py`** | Python `dataclasses` + `enum` | Maintains per-student records (`StudentRecord`), suspicious score accumulation, violation cooldowns, presence state transitions (*Present*, *Temporarily Missing*, *Warning Missing*, *Exited*), and **dynamic personal gaze baseline calibration**. | **Well-Engineered** |
| **`dashboard.py`** | Flask + Multi-threading + `CentroidTracker` | Coordinates live video streaming via MJPEG (`/video_feed`), background inference loop, auto-assignment of student IDs (`CentroidTracker`), exam pause/resume state (`ExamControl`), count change alerts, and snapshot APIs (`/api/status`). | **Working, but contains tech debt** |
| **`templates/index.html`** | Vanilla JS + Modern CSS (dark mode) | Real-time monitoring UI with student cards, visual alerts, violation thumbnail popups, FPS badges, and optional track relabeling. | **Polished** |

---

## 3. Working Capabilities & Innovation Highlights

1. **Auto-ID Multi-Student Tracking:**
   - Detects multiple individuals without pre-configuration.
   - `CentroidTracker` assigns persistent IDs (`AUTO-0`, `AUTO-1`, ...) with centroid distance matching across frames.
   - Allows optional cosmetic relabeling via web UI (`/api/assign_student`) to bind student college IDs and names.

2. **Per-Student Gaze Baseline Calibration (EMA):**
   - Traditional gaze algorithms use hardcoded thresholds (e.g. 0.5 center ratio) that produce false positives due to lighting, head shapes, or eyeglasses.
   - The engine automatically updates an Exponential Moving Average (`gaze_baseline_h`) only when head pose is centered (|yaw| < 8 deg).
   - Sideways gaze violations are triggered only when the ratio deviates significantly from the student's own established baseline (> 0.12).

3. **Seat-Anchored Boundary Zones:**
   - Rather than measuring distance between adjacent students (which fails due to camera perspective compression in row seating), the system anchors virtual circular zones around each student's calibrated desk location.
   - Scale is normalized by each student's observed `torso_length`.

4. **Exam Continuity & Invigilator Control (`ExamControl`):**
   - Manual Pause/Resume functionality freezes violation scoring while maintaining live video feed.
   - **Auto-Pause on Count Change:** Automatically halts scoring and displays an invigilator alert if the number of detected students shifts (e.g. a student leaves the room or an unauthorized person enters).

5. **Evidence Trail:**
   - Automatically crops/saves timestamped violation frames into the `evidence/` directory, linking thumbnails directly to student event logs in the dashboard.

---

## 4. Current Problems, Technical Debt & Critical Bugs

### 4.1. Critical Functional Bugs

1. **Gaze Association Mismatch in Multi-Student Mode (`dashboard.py:1341-1345`):**
   - In `dashboard.py`:
     ```python
     gazes = gaze_est.estimate(frame)
     ...
     gaze_dir, gaze_h_ratio = None, None
     if gazes:
         gaze_dir     = gazes[0]["gaze_direction"]
         gaze_h_ratio = gazes[0]["horizontal_ratio"]
     ```
   - **The Bug:** Inside the loop over all tracked students (`for p in people_with_pose`), the system assigns `gazes[0]` to **every student**.
   - Unlike head pose (which computes Euclidean distance between nose keypoint and person centroid), gaze estimation is not mapped to the corresponding face or person bounding box. If Student 1 looks straight and Student 2 looks left, Student 1 could be penalized with Student 2's gaze values.

2. **Dual MediaPipe FaceMesh Redundancy (Major Performance Killer):**
   - `HeadPoseEstimator` initializes an independent instance of `mp.solutions.face_mesh.FaceMesh(refine_landmarks=False)`.
   - `EyeGazeEstimator` initializes a second independent instance of `mp.solutions.face_mesh.FaceMesh(refine_landmarks=True)`.
   - **Result:** Every single video frame runs MediaPipe Face Mesh **twice**. Because iris refinement in the gaze estimator already includes all 468 facial mesh landmarks, both head pose and eye gaze can be computed from a **single FaceMesh pass**, which would instantly double inference throughput.

3. **Head Pose Distance Thresholding (`dashboard.py:1332`):**
   - `dist < 300` pixels is used to match a face pose to a person centroid.
   - In high-resolution video (1280x720) or wide-angle camera feeds, 300px can erroneously match an adjacent student sitting closely in the next chair, or fail if a tall student is seated close to the lens.

### 4.2. Codebase Organization & Technical Debt

1. **Dead Code in `dashboard.py` (~900 lines of commented code):**
   - Lines 1-426 contain the legacy single-student dashboard.
   - Lines 427-910 contain an intermediate manual-registration version.
   - Active code only starts at line 911. This inflates file size to 67 KB and creates confusion for maintainers and academic reviewers.

2. **Volatile In-Memory State (No Database / Export):**
   - All student tracking data, violations, and calibration baselines exist only in Python memory (`student_registry`, `StudentScoringEngine.students`).
   - If the server restarts or crashes, all exam session data is lost.
   - There is no CSV/JSON/PDF export feature for final post-exam reporting.

3. **Centroid Tracking Fragility:**
   - The centroid tracker uses simple Euclidean distance thresholding (max 150 px).
   - If a student stands up, stretches, or is temporarily occluded by another student walking past, IDs can easily switch or duplicate, splitting their penalty score across multiple auto-IDs.

4. **Limited Prohibited Object Detection:**
   - `ObjectDetector` relies strictly on COCO weights (`cell phone` class 67).
   - It cannot detect smartwatches, paper cheat sheets, earbuds, or secondary digital notes without custom training.

5. **2D Distortion in Desk Zones:**
   - Desk zones are rendered as 2D Euclidean circles on the image plane.
   - Due to perspective projection, a circular desk area appears elliptical and smaller for distant rows, causing false zone violations for students seated farther from the camera.

---

## 5. Test Suite Evaluation

The repository includes extensive standalone test scripts:

| Test Script | Target Verification | Notes |
| :--- | :--- | :--- |
| `test_face_detection.py` | MediaPipe Face Detection + bounding boxes | Validates camera feed and confidence scores. |
| `test_head_pose.py` | MediaPipe FaceMesh + `solvePnP` | Visualizes nose direction vector and yaw/pitch/roll. |
| `test_eye_gaze.py` | Iris ratios and direction classification | Tests horizontal and vertical iris tracking. |
| `test_person_pose.py` | YOLOv8 Person + MediaPipe Pose ROI cropping | Verifies shoulder/hip landmark detection and spine tilt. |
| `test_boundary.py` | `BoundaryZoneAnalyzer` spine tilt classification | Tests multi-person leaning status without seat anchoring. |
| `test_desk_zones.py` | `DeskZoneManager` 30-frame seat calibration | Verifies seat anchoring and violation circles. |
| `test_object_detection.py`| YOLOv8 phone detection | Tests phone bounding box overlays and alert flags. |
| `test_integrated.py` | Complete pipeline via OpenCV GUI (Single student) | Excellent standalone HUD test; good benchmark before launching Flask. |

*Note: All current test scripts require a physical camera and graphical display (`cv2.imshow`), meaning there are no automated headless unit tests (e.g. `pytest` fixtures on recorded video clips or synthetic frames).*

---

## 6. Recommendations for Graduation Project Completion

### Priority 1: Bug Fixes & Optimization (Immediate)
1. **Unify FaceMesh:** Merge `HeadPoseEstimator` and `EyeGazeEstimator` into a single wrapper that processes `FaceMesh(refine_landmarks=True)` once per frame. This will provide an immediate 30-50% FPS boost.
2. **Fix Multi-Student Gaze Association:** Associate facial landmarks and iris detections with the bounding box of each specific person (matching face centroid to person upper bounding box).
3. **Clean Up `dashboard.py`:** Delete the 910 lines of commented legacy code and keep only the active implementation.

### Priority 2: Academic & Presentation Features (High Impact for Defense)
1. **Exam Session Report Generator:** Add a "Finish Exam and Export Report" button in the dashboard that exports a clean PDF or CSV summary with student names, total scores, final status (Clean/Suspicious), and violation event timestamps with evidence photos.
2. **Zone Recalibration Button:** Add an API endpoint (`/api/recalibrate_zones`) so the proctor can re-trigger the 30-frame desk zone calibration without restarting the server.
3. **Recorded Video Test Mode:** Allow passing a video file path (e.g. `--video test_footage.mp4`) instead of requiring a live webcam, making live demo presentations at the university defense predictable and robust.

### Priority 3: Architecture Maturation (Future Work Chapter in Thesis)
- Integrate Re-ID embeddings (e.g. ByteTrack or DeepSORT) to prevent student ID swapping during occlusion.
- Custom dataset fine-tuning on YOLOv8 for smartwatches, Bluetooth earbuds, and exam paper notes.
- Perspective transform (homography) to map camera view to a bird's-eye floor plan for accurate desk zone tracking.

---

## 7. Current Project Status Verdict

| Criteria | Assessment | Comment |
| :--- | :---: | :--- |
| **Concept & Feasibility** | **Excellent (9/10)** | Directly addresses academic proctoring needs with multimodal computer vision. |
| **Feature Completeness (PoC)** | **Strong (8/10)** | Includes face, head pose, eye gaze, body pose, desk boundaries, phone detection, and web dashboard. |
| **Code Structure & Modularity** | **Good (7/10)** | Well-separated module files, clean dataclasses, though `dashboard.py` requires dead code cleanup. |
| **Multi-Student Robustness** | **Moderate (5.5/10)** | Spatial matching between gaze and person tracks requires the fix documented above. |
| **Performance Efficiency** | **Moderate (6/10)** | Redundant FaceMesh calls cause lower frame rates on non-GPU setups. |
| **Ready for Final Defense** | **Requires Polish** | Ready for demo after unifying FaceMesh, fixing multi-student gaze assignment, and cleaning up `dashboard.py`. |
