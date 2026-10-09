export interface User {
  id: number;
  username: string;
  email?: string;
  role: string;
}

export interface ViolationEvent {
  id: number;
  track_id?: number;
  student_name?: string;
  student_college_id?: string;
  event_type: string;
  points: number;
  total_score?: number;
  is_suspicious?: boolean;
  evidence_url?: string;
  timestamp: string;
}

export interface StudentTrack {
  track_id: number;
  student_college_id?: string;
  student_name?: string;
  score: number;
  is_suspicious: boolean;
  presence_state: string;
  head_yaw: number;
  head_pitch: number;
  gaze_direction: string;
  gaze_baseline_h?: number;
  zone_status: string;
  events?: ViolationEvent[];
}

export interface ExamSession {
  id: number;
  title: string;
  room_name: string;
  status: "running" | "paused" | "completed";
  pause_reason?: string;
  student_count: number;
}

export interface RobotStatus {
  device_code: string;
  status: string;
  battery_level: number;
  current_zone: string;
  last_ping: string;
}
