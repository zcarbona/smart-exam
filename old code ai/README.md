# Smart Exam Proctoring System

A Python computer-vision system that monitors students during an exam through a
webcam and flags suspicious behavior in real time — head turns, eye gaze away from
the screen, phone detection, multiple faces, leaning toward another student, and
leaving the desk zone. Built with **OpenCV**, **MediaPipe**, and **YOLOv8**, with
a live **Flask** web dashboard.

## Features

- 👤 Face detection + head pose estimation (yaw/pitch)
- 👁 Eye gaze tracking with a per-student calibrated baseline
- 🧍 Person detection, pose estimation, and desk-zone boundary checks
- 📱 Phone / object detection (YOLOv8)
- 🔢 Multi-student tracking — each detected person gets an automatic ID, no manual setup
- ⏸ Pause / Resume — manually pause the exam, or it auto-pauses when the number of
  detected students changes (so the proctor can confirm before scoring continues)
- 📊 Live web dashboard — per-student score, violation events, and evidence screenshots
- 📷 Works with a built-in webcam or an iPhone via Continuity Camera

## Requirements

- Python 3.10+
- A webcam (built-in, USB, or iPhone via Continuity Camera)

## Setup

```bash
# 1. Clone the repo
git clone <your-repo-url>
cd <repo-folder>

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the dashboard
python dashboard.py
```

Then open **http://127.0.0.1:5001** in your browser.

## Using an iPhone as the camera

```bash
python3 -c "from camera_capture import list_available_cameras; print(list_available_cameras())"
```

This prints the available camera indices. Update `CAMERA_INDEX` near the top of
`dashboard.py` with the iPhone's index (usually `1` or `2`, not `0`).

## Project Structure

```
.
├── dashboard.py          # Main app: detection loop + Flask web dashboard
├── camera_capture.py     # Webcam / iPhone camera wrapper
├── face_detector.py      # Face detection + head pose estimation
├── eye_gaze.py           # Eye gaze tracking
├── person_detector.py    # Person detection + pose estimation
├── boundary_zones.py     # Desk zone setup + leaning/boundary checks
├── object_detector.py    # Phone / object detection (YOLOv8)
├── scoring_system.py     # Per-student scoring engine
├── templates/
│   └── index.html        # Live dashboard UI
├── requirements.txt
└── yolov8n.pt             # YOLOv8 model weights
```

## Notes

- On first run, the system spends ~30 frames calibrating desk zones — keep
  students seated still during this phase.
- This is a graduation project / proof of concept, not a production exam
  security tool. Detection accuracy depends heavily on camera angle and lighting.
