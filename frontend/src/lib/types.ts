export type UserRole = 'admin' | 'invigilator';

export interface User {
  id: number;
  username: string;
  email?: string | null;
  role: UserRole;
  is_active: boolean;
  full_name?: string | null;
  assigned_room_id?: number | null;
  created_at?: string;
}

export interface ViolationEvent {
  id: number;
  track_id?: number;
  student_name?: string | null;
  student_college_id?: string | null;
  event_type: string;
  points: number;
  total_score?: number | null;
  is_suspicious?: boolean | null;
  evidence_url?: string | null;
  timestamp: string;
}

export interface StudentTrack {
  track_id: number;
  student_college_id?: string | null;
  student_name?: string | null;
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
  room_id?: number | null;
  status: 'running' | 'paused' | 'completed';
  pause_reason?: string | null;
  student_count: number;
}

export interface RobotStatus {
  device_code: string;
  status: string;
  battery_level: number;
  current_zone: string;
  last_ping: string;
}

export interface ExamRoom {
  id: number;
  room_code: string;
  name: string;
  building?: string | null;
  is_active: boolean;
}

export interface CameraStatus {
  id: number;
  room_id: number;
  name: string;
  device_code: string;
  status: 'online' | 'offline' | 'unknown';
  last_seen_at?: string | null;
  last_error?: string | null;
}

export interface DashboardStats {
  active_exams: number;
  paused_exams: number;
  tracked_students: number;
  suspicious_students: number;
  total_events: number;
  events_last_hour: number;
  events_today: number;
  cameras_total: number;
  cameras_online: number;
  cameras_offline: number;
  cameras_unknown: number;
  robots_total: number;
  robots_online: number;
  event_type_breakdown: { event_type: string; count: number }[];
}

export interface Invigilator {
  id: number;
  username: string;
  email?: string | null;
  role: UserRole;
  is_active: boolean;
  full_name?: string | null;
  assigned_room_id?: number | null;
  created_at?: string;
}

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

/** `null` means "no record exists" — the backend never fabricates one. */
export type MaybeNull<T> = T | null;
