import time
from dataclasses import dataclass, field
from enum import Enum


class PresenceState(Enum):
    PRESENT = "present"
    TEMPORARILY_MISSING = "temporarily_missing"
    WARNING_MISSING = "warning_missing"
    EXITED = "exited"


@dataclass
class ScoringRules:
    """
    Point values for each violation type.
    Calibrate these based on real exam footage.
    """
    looking_sideways: int = 1
    looking_down_sustained: int = 2
    mobile_detected: int = 5
    another_face_detected: int = 5
    leaning_violation: int = 4
    desk_zone_violation: int = 4
    detection_lost: int = 1
    suspicious_score_threshold: int = 10

    # Timing thresholds (seconds)
    looking_down_duration_threshold: float = 5.0
    looking_sideways_cooldown: float = 3.0
    detection_failure_cooldown: float = 3.0
    temporarily_missing_threshold: float = 10.0
    warning_missing_threshold: float = 30.0

    # ── Personal gaze calibration settings ────────────────────────────
    # Head must be within +/- this many degrees of center to count as
    # a valid "centered" sample for updating the personal gaze baseline.
    gaze_baseline_yaw_threshold: float = 8.0

    # How fast the rolling baseline adapts to new centered samples.
    # Lower = slower/more stable, higher = adapts faster but noisier.
    gaze_baseline_smoothing: float = 0.05

    # How far the current gaze ratio must deviate from the student's
    # OWN calibrated baseline to count as "looking away" in that direction.
    gaze_deviation_threshold: float = 0.12


@dataclass
class StudentRecord:
    """Tracks ongoing state for a single student across frames."""
    student_id: int
    score: float = 0.0
    presence_state: PresenceState = PresenceState.PRESENT
    last_seen_timestamp: float = field(default_factory=time.time)
    looking_down_since: float = None
    last_sideways_timestamp: float = None
    last_failure_timestamp: float = None
    # Each entry: (timestamp, event_name, points, evidence_path)
    event_log: list = field(default_factory=list)

    # ── Personal gaze baseline (auto-calibrated) ──────────────────────
    # Continuously updated whenever the head is centered, so it adapts
    # to glasses, lighting, and individual eye shape without requiring
    # an explicit calibration step.
    gaze_baseline_h: float = 0.5
    gaze_baseline_samples: int = 0

    def is_suspicious(self, threshold: float) -> bool:
        return self.score > threshold


class StudentScoringEngine:
    """
    Combines outputs from all detection modules into a single per-student
    suspicious score, and manages a presence state machine.

    State Machine:
        Present -> Temporarily Missing (0-10s) -> Warning Missing (10-30s) -> Exited (>30s)

    Sideways detection logic:
        Violation is confirmed when head yaw exceeds a threshold AND the
        eye gaze deviates from the student's OWN personal baseline in the
        same direction. The baseline is continuously auto-calibrated
        whenever the head is roughly centered, so no explicit calibration
        step is required and it adapts over time (lighting changes, glasses
        glare, posture shifts, etc).

        If gaze ratio data is not available, falls back to head-only
        detection. If the baseline has not been established yet, falls back
        to the fixed "Eyes Left"/"Eyes Right" label comparison.

    Detection failure logic:
        When the head pose estimator fails to detect a pose while a face
        IS present in the frame, this likely means the student is turned
        at an extreme angle (possible cheating) or lighting is very poor.
        A small score penalty is added with a cooldown to avoid spamming.

    Each logged event optionally carries an evidence_path (e.g. a saved
    screenshot filepath) for dashboard display.
    """

    def __init__(self, rules: ScoringRules = None):
        self.rules = rules or ScoringRules()
        self.students: dict[int, StudentRecord] = {}

    def _get_or_create_record(self, student_id: int) -> StudentRecord:
        if student_id not in self.students:
            self.students[student_id] = StudentRecord(student_id=student_id)
        return self.students[student_id]

    # ────────────────────────────────────────────────────────────────────
    # Presence State Machine
    # ────────────────────────────────────────────────────────────────────

    def update_presence(self, student_id: int, is_detected: bool) -> StudentRecord:
        """
        Call every frame for every tracked student, whether detected or not.
        Drives the presence state machine and timestamps last-seen.
        """
        record = self._get_or_create_record(student_id)
        now = time.time()

        if is_detected:
            record.last_seen_timestamp = now
            record.presence_state = PresenceState.PRESENT
            return record

        missing_duration = now - record.last_seen_timestamp

        if missing_duration < self.rules.temporarily_missing_threshold:
            record.presence_state = PresenceState.TEMPORARILY_MISSING

        elif missing_duration < self.rules.warning_missing_threshold:
            if record.presence_state != PresenceState.WARNING_MISSING:
                self._add_event(record, "leaving_seat", self.rules.leaning_violation)
            record.presence_state = PresenceState.WARNING_MISSING

        else:
            record.presence_state = PresenceState.EXITED

        return record

    # ────────────────────────────────────────────────────────────────────
    # Head Pose + Eye Gaze (combined, with personal gaze calibration)
    # ────────────────────────────────────────────────────────────────────

    def update_head_pose(self, student_id: int, yaw: float, pitch: float,
                         gaze_direction: str = None,
                         gaze_horizontal_ratio: float = None,
                         yaw_threshold: float = 20.0,
                         pitch_down_threshold: float = -15.0):
        """
        Call once per frame with the student's head yaw/pitch and (optionally)
        eye gaze info from EyeGazeEstimator.

        gaze_horizontal_ratio: raw horizontal_ratio value from EyeGazeEstimator
        (0.0-1.0). Used to auto-calibrate a personal baseline whenever the head
        is roughly centered (within gaze_baseline_yaw_threshold degrees), and
        to detect deviation from that baseline when checking for sideways looks.

        Looking down logic:
            - Pitch must be below pitch_down_threshold continuously
            - Points added only after looking_down_duration_threshold seconds
            - Re-triggers every N seconds if sustained
        """
        record = self._get_or_create_record(student_id)
        now = time.time()

        # ── Auto-calibrate personal gaze baseline when head is centered ────
        if gaze_horizontal_ratio is not None and abs(yaw) < self.rules.gaze_baseline_yaw_threshold:
            alpha = self.rules.gaze_baseline_smoothing
            if record.gaze_baseline_samples == 0:
                # First sample — initialize directly instead of blending with default 0.5
                record.gaze_baseline_h = gaze_horizontal_ratio
            else:
                # Exponential moving average — slowly adapts to the student's natural center
                record.gaze_baseline_h = (
                    (1 - alpha) * record.gaze_baseline_h + alpha * gaze_horizontal_ratio
                )
            record.gaze_baseline_samples += 1

        # ── Sideways detection ───────────────────────────────────────────
        if abs(yaw) > yaw_threshold:
            is_looking_right = yaw > 0
            is_looking_left = yaw < 0

            if gaze_direction is None:
                # No gaze data available at all — use head yaw alone
                gaze_confirms = True
            elif gaze_horizontal_ratio is not None and record.gaze_baseline_samples > 0:
                # Compare against THIS student's personal baseline, not a fixed 0.5
                deviation = gaze_horizontal_ratio - record.gaze_baseline_h
                if is_looking_right and deviation > self.rules.gaze_deviation_threshold:
                    gaze_confirms = True
                elif is_looking_left and deviation < -self.rules.gaze_deviation_threshold:
                    gaze_confirms = True
                else:
                    gaze_confirms = False
            else:
                # Not calibrated yet — fall back to fixed label comparison
                if is_looking_right and gaze_direction == "Eyes Right":
                    gaze_confirms = True
                elif is_looking_left and gaze_direction == "Eyes Left":
                    gaze_confirms = True
                else:
                    gaze_confirms = False

            if gaze_confirms:
                last = record.last_sideways_timestamp
                cooldown_passed = (last is None) or (
                    (now - last) >= self.rules.looking_sideways_cooldown
                )
                if cooldown_passed:
                    direction_label = "right" if is_looking_right else "left"
                    self._add_event(
                        record,
                        f"looking_sideways_{direction_label}",
                        self.rules.looking_sideways,
                    )
                    record.last_sideways_timestamp = now
        else:
            record.last_sideways_timestamp = None

        # ── Looking down (sustained) ─────────────────────────────────────
        if pitch < pitch_down_threshold:
            if record.looking_down_since is None:
                record.looking_down_since = now
            elif (now - record.looking_down_since) >= self.rules.looking_down_duration_threshold:
                self._add_event(record, "looking_down_sustained", self.rules.looking_down_sustained)
                record.looking_down_since = now
        else:
            record.looking_down_since = None

    # ────────────────────────────────────────────────────────────────────
    # Detection Failure
    # ────────────────────────────────────────────────────────────────────

    def report_detection_failure(self, student_id: int):
        """
        Call when head pose estimation fails while a face IS present in
        the frame. This usually means the student has turned to an extreme
        angle (strong cheating signal) or lighting is very poor.

        A cooldown prevents this from spamming the event log every frame.
        """
        record = self._get_or_create_record(student_id)
        now = time.time()
        last = record.last_failure_timestamp
        cooldown = self.rules.detection_failure_cooldown

        if last is None or (now - last) >= cooldown:
            self._add_event(record, "detection_lost", self.rules.detection_lost)
            record.last_failure_timestamp = now

    # ────────────────────────────────────────────────────────────────────
    # Event Reporters
    # ────────────────────────────────────────────────────────────────────

    def report_mobile_detected(self, student_id: int):
        """Call when a mobile phone is detected near this student."""
        record = self._get_or_create_record(student_id)
        self._add_event(record, "mobile_detected", self.rules.mobile_detected)

    def report_another_face(self, student_id: int):
        """Call when more than one face is detected in this student's area."""
        record = self._get_or_create_record(student_id)
        self._add_event(record, "another_face_detected", self.rules.another_face_detected)

    def report_leaning_violation(self, student_id: int):
        """Call when BoundaryZoneAnalyzer reports 'violation' for this student."""
        record = self._get_or_create_record(student_id)
        self._add_event(record, "leaning_violation", self.rules.leaning_violation)

    def report_desk_zone_violation(self, student_id: int):
        """Call when DeskZoneManager reports 'violation' for this student."""
        record = self._get_or_create_record(student_id)
        self._add_event(record, "desk_zone_violation", self.rules.desk_zone_violation)

    # ────────────────────────────────────────────────────────────────────
    # Internal
    # ────────────────────────────────────────────────────────────────────

    def _add_event(self, record: StudentRecord, event_name: str, points: int,
                   evidence_path: str = None):
        """
        Appends a new violation event to the student's log.
        evidence_path starts as None and may be filled in later (e.g. by
        the dashboard, which saves a screenshot and updates this entry).
        """
        record.score += points
        record.event_log.append((time.time(), event_name, points, evidence_path))

    # ────────────────────────────────────────────────────────────────────
    # Queries
    # ────────────────────────────────────────────────────────────────────

    def get_record(self, student_id: int) -> StudentRecord:
        return self._get_or_create_record(student_id)

    def get_all_records(self) -> list[StudentRecord]:
        return list(self.students.values())

    def get_suspicious_students(self) -> list[StudentRecord]:
        threshold = self.rules.suspicious_score_threshold
        return [r for r in self.students.values() if r.is_suspicious(threshold)]

    def reset_student(self, student_id: int):
        """Reset a student's score and state (e.g. for a new exam session)."""
        self.students[student_id] = StudentRecord(student_id=student_id)

    def reset_all(self):
        """Reset all students (new exam session)."""
        self.students.clear()