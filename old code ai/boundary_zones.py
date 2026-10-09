import itertools
from dataclasses import dataclass


@dataclass
class ZoneThresholds:
    """
    Desk zone size and spine-tilt thresholds, expressed as multiples of
    torso_length (normalized) where applicable.
    """
    safe_radius_multiplier: float = 1.5     # zone radius = 1.5x torso_length
    warning_radius_multiplier: float = 2.2  # beyond this = violation (left the desk)

    spine_tilt_warning_deg: float = 15.0
    spine_tilt_violation_deg: float = 25.0


class DeskZoneManager:
    """
    Generates and tracks a virtual "desk zone" (a circular safe area) for
    each student, anchored to their position during the setup frames at the
    start of the exam. Each frame afterward, checks whether each student's
    body center is still within their own assigned zone.

    This avoids relying on distance-to-other-students (which breaks down when
    students are in different rows, front/back from the camera's perspective)
    and instead checks each student against their OWN fixed seat location.
    """

    def __init__(self, thresholds: ZoneThresholds = None, setup_frames: int = 30):
        self.thresholds = thresholds or ZoneThresholds()
        self.setup_frames = setup_frames  # how many frames to average for initial positions
        self.zones = {}          # zone_id -> {"center": (x, y), "radius": float}
        self._setup_buffer = []  # collected (center, torso_length) during setup
        self._is_setup_complete = False
        self._frames_seen = 0

    @property
    def is_setup_complete(self):
        return self._is_setup_complete

    def setup_frame(self, people_with_pose: list):
        """
        Call this once per frame ONLY during the setup phase (e.g. first
        N frames when students are known to be seated correctly).

        people_with_pose: list of dicts with "pose" containing
        "shoulder_center" and "torso_length" (same format as BoundaryZoneAnalyzer input).

        Returns True once setup is complete (zones have been generated).
        """
        if self._is_setup_complete:
            return True

        valid_people = [p for p in people_with_pose if p.get("pose") is not None]
        self._setup_buffer.append(valid_people)
        self._frames_seen += 1

        if self._frames_seen >= self.setup_frames:
            self._finalize_zones()
            self._is_setup_complete = True

        return self._is_setup_complete

    def _finalize_zones(self):
        """
        Average the positions seen across all setup frames to get a stable
        seat location per student, then assign each one a permanent zone_id.

        Uses the LAST setup frame's detections as the canonical list of seats,
        then matches earlier frames to those seats by nearest distance to
        compute a more stable average center.
        """
        if not self._setup_buffer or not self._setup_buffer[-1]:
            return  # no people detected during setup — nothing to do

        reference_people = self._setup_buffer[-1]

        # Initialize accumulators using the last frame as the seat reference
        accumulators = []
        for person in reference_people:
            accumulators.append({
                "centers": [person["pose"]["shoulder_center"]],
                "torsos": [person["pose"]["torso_length"]],
            })

        # Match earlier frames to these reference seats by nearest center
        for frame_people in self._setup_buffer[:-1]:
            for person in frame_people:
                center = person["pose"]["shoulder_center"]
                closest_idx = self._find_closest_accumulator(center, accumulators)
                if closest_idx is not None:
                    accumulators[closest_idx]["centers"].append(center)
                    accumulators[closest_idx]["torsos"].append(person["pose"]["torso_length"])

        # Finalize: average each accumulator into a zone
        for zone_id, acc in enumerate(accumulators):
            avg_x = sum(c[0] for c in acc["centers"]) / len(acc["centers"])
            avg_y = sum(c[1] for c in acc["centers"]) / len(acc["centers"])
            avg_torso = sum(acc["torsos"]) / len(acc["torsos"])

            self.zones[zone_id] = {
                "center": (avg_x, avg_y),
                "torso_length": avg_torso,
                "safe_radius": avg_torso * self.thresholds.safe_radius_multiplier,
                "violation_radius": avg_torso * self.thresholds.warning_radius_multiplier,
            }

    @staticmethod
    def _find_closest_accumulator(center, accumulators, max_distance=300):
        """Find the accumulator whose latest center is closest to `center`."""
        best_idx = None
        best_dist = max_distance
        for idx, acc in enumerate(accumulators):
            last_center = acc["centers"][-1]
            dist = ((center[0] - last_center[0]) ** 2 + (center[1] - last_center[1]) ** 2) ** 0.5
            if dist < best_dist:
                best_dist = dist
                best_idx = idx
        return best_idx

    def check_zones(self, people_with_pose: list):
        """
        Call this once per frame AFTER setup is complete.

        For each detected person, finds their assigned zone (by nearest
        match to a zone center) and checks whether their current body
        center is still within the safe radius.

        Returns a list of dicts:
            {
                "zone_id": int,
                "person_bbox": (x1, y1, x2, y2),
                "current_center": (x, y),
                "zone_center": (x, y),
                "distance_from_zone_center": float,    # raw pixels
                "normalized_distance": float,          # in torso-length units
                "status": "safe" | "warning" | "violation" | "unassigned",
            }
        """
        if not self._is_setup_complete:
            raise RuntimeError("Zones not set up yet. Call setup_frame() until is_setup_complete is True.")

        results = []
        for person in people_with_pose:
            if person.get("pose") is None:
                continue

            current_center = person["pose"]["shoulder_center"]
            zone_id, zone = self._match_to_zone(current_center)

            if zone is None:
                results.append({
                    "zone_id": None,
                    "person_bbox": person["bbox"],
                    "current_center": current_center,
                    "zone_center": None,
                    "distance_from_zone_center": None,
                    "normalized_distance": None,
                    "status": "unassigned",  # student wasn't present during setup (e.g. arrived late)
                })
                continue

            raw_distance = self._euclidean_distance(current_center, zone["center"])
            normalized_distance = raw_distance / zone["torso_length"] if zone["torso_length"] > 1e-6 else 0.0

            if raw_distance <= zone["safe_radius"]:
                status = "safe"
            elif raw_distance <= zone["violation_radius"]:
                status = "warning"
            else:
                status = "violation"

            results.append({
                "zone_id": zone_id,
                "person_bbox": person["bbox"],
                "current_center": current_center,
                "zone_center": zone["center"],
                "distance_from_zone_center": raw_distance,
                "normalized_distance": normalized_distance,
                "status": status,
            })

        return results

    def _match_to_zone(self, current_center):
        """Find the nearest zone to a given point. Returns (zone_id, zone_dict) or (None, None)."""
        best_id = None
        best_zone = None
        best_dist = float("inf")

        for zone_id, zone in self.zones.items():
            dist = self._euclidean_distance(current_center, zone["center"])
            if dist < best_dist:
                best_dist = dist
                best_id = zone_id
                best_zone = zone

        return best_id, best_zone

    @staticmethod
    def _euclidean_distance(point_a, point_b):
        ax, ay = point_a
        bx, by = point_b
        return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5


class BoundaryZoneAnalyzer:
    """
    Kept separate from desk-zone logic: analyzes individual leaning/posture
    (spine tilt) — this part is per-student and doesn't depend on seat position,
    so it works independently of DeskZoneManager.
    """

    def __init__(self, thresholds: ZoneThresholds = None):
        self.thresholds = thresholds or ZoneThresholds()

    def analyze_leaning(self, people_with_pose: list):
        """
        Returns a list of dicts:
            {
                "person_bbox": (x1, y1, x2, y2),
                "spine_tilt_degrees": float,
                "leaning_status": "safe" | "warning" | "violation",
            }
        """
        results = []
        for person in people_with_pose:
            if person.get("pose") is None:
                continue

            tilt = abs(person["pose"]["spine_tilt_degrees"])
            status = self._classify_tilt(tilt)

            results.append({
                "person_bbox": person["bbox"],
                "spine_tilt_degrees": person["pose"]["spine_tilt_degrees"],
                "leaning_status": status,
            })

        return results

    def _classify_tilt(self, abs_tilt_degrees):
        t = self.thresholds
        if abs_tilt_degrees < t.spine_tilt_warning_deg:
            return "safe"
        elif abs_tilt_degrees < t.spine_tilt_violation_deg:
            return "warning"
        else:
            return "violation"