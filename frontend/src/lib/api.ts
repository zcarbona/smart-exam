import type {
  AuthTokens,
  CameraStatus,
  DashboardStats,
  ExamRoom,
  ExamSession,
  Invigilator,
  RobotStatus,
  StudentTrack,
  User,
  ViolationEvent,
} from './types';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

/** Exported so UI code can build absolute evidence/asset URLs without
 * hard-coding a host, which previously duplicated "localhost:8000". */
export { API_BASE };

const TOKEN_KEY = 'smartexam_token';
const REFRESH_TOKEN_KEY = 'smartexam_refresh_token';

/** Error carrying the HTTP status so callers can distinguish 401/403/400. */
export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

export function isForbidden(err: unknown): boolean {
  return err instanceof ApiError && err.status === 403;
}

export function isUnauthorized(err: unknown): boolean {
  return err instanceof ApiError && err.status === 401;
}

let refreshHandler: (() => Promise<string | null>) | null = null;
let onSessionLost: (() => void) | null = null;

export function registerAuthRefresh(handler: () => Promise<string | null>) {
  refreshHandler = handler;
}

/** Called when a refresh attempt fails, so the app can clear state once. */
export function registerSessionLostHandler(handler: () => void) {
  onSessionLost = handler;
}

export function getAccessToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function getRefreshToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

export function storeTokens(access: string, refresh: string) {
  if (typeof window === 'undefined') return;
  localStorage.setItem(TOKEN_KEY, access);
  localStorage.setItem(REFRESH_TOKEN_KEY, refresh);
}

export function clearTokens() {
  if (typeof window === 'undefined') return;
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}

export function storeUser(user: User) {
  if (typeof window === 'undefined') return;
  // Cached for instant rendering only. It is never the authority for
  // authorization decisions — every request is re-validated server-side.
  localStorage.setItem('smartexam_user', JSON.stringify(user));
}

export function clearUser() {
  if (typeof window === 'undefined') return;
  localStorage.removeItem('smartexam_user');
}

async function parseError(response: Response, fallback: string): Promise<string> {
  try {
    const body = await response.json();
    const detail = body?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) return detail.map((d) => d?.msg).filter(Boolean).join(', ') || fallback;
  } catch {
    // Response had no JSON body.
  }
  return fallback;
}

export async function apiRequest<T = any>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const makeRequest = (token: string | null) => {
    const headers = new Headers(options.headers || {});
    if (token && !headers.has('Authorization')) {
      headers.set('Authorization', `Bearer ${token}`);
    }
    if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
      headers.set('Content-Type', 'application/json');
    }
    return fetch(`${API_BASE}${endpoint}`, { ...options, headers });
  };

  let response = await makeRequest(getAccessToken());

  // Automatic token refresh on 401 if refresh handler is registered
  if (response.status === 401 && refreshHandler) {
    const newToken = await refreshHandler();
    if (newToken) {
      response = await makeRequest(newToken);
    }
  }

  if (!response.ok) {
    // A 401 after a failed refresh means the session is genuinely gone.
    if (response.status === 401) {
      onSessionLost?.();
    }
    throw new ApiError(response.status, await parseError(response, `Request failed (${response.status})`));
  }

  if (response.status === 204) return undefined as T;
  return response.json();
}

// ---------------------------------------------------------------- auth

export async function login(username: string, password: string): Promise<AuthTokens> {
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    throw new ApiError(res.status, await parseError(res, 'Failed to login'));
  }
  return res.json();
}

export async function refreshToken(refreshTokenStr: string): Promise<AuthTokens> {
  const res = await fetch(`${API_BASE}/api/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshTokenStr }),
  });
  if (!res.ok) {
    throw new ApiError(res.status, await parseError(res, 'Refresh token expired or invalid'));
  }
  return res.json();
}

/** Fetches the identity the server actually resolved for this token. */
export async function fetchCurrentUser(token?: string): Promise<User> {
  const headers: HeadersInit = token ? { Authorization: `Bearer ${token}` } : {};
  const res = await apiRequest<User>('/api/auth/me', { headers });
  return res;
}

export async function logoutRequest(): Promise<void> {
  try {
    await apiRequest('/api/auth/logout', { method: 'POST' });
  } catch {
    // Local teardown proceeds regardless: clearing the client cannot fail.
  }
}

// ---------------------------------------------------------------- exams

export async function getExamStatus(): Promise<ExamSession | null> {
  return apiRequest<ExamSession | null>('/api/exams/status');
}

export async function startExam(payload: { title?: string; room_id?: number; room_name?: string }) {
  return apiRequest<ExamSession>('/api/exams/start', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function pauseExam(reason = 'Proctor paused exam') {
  return apiRequest<ExamSession>(`/api/exams/pause?reason=${encodeURIComponent(reason)}`, {
    method: 'POST',
  });
}

export async function resumeExam() {
  return apiRequest<ExamSession>('/api/exams/resume', { method: 'POST' });
}

export async function getStudents(): Promise<StudentTrack[]> {
  return apiRequest<StudentTrack[]>('/api/exams/students');
}

export async function assignStudent(trackId: number, studentCollegeId: string, studentName: string) {
  return apiRequest('/api/exams/assign-student', {
    method: 'POST',
    body: JSON.stringify({
      track_id: trackId,
      student_college_id: studentCollegeId,
      student_name: studentName,
    }),
  });
}

// ---------------------------------------------------------------- events / stats

export async function getRecentEvents(limit = 50): Promise<ViolationEvent[]> {
  return apiRequest<ViolationEvent[]>(`/api/events/recent?limit=${limit}`);
}

export async function getDashboardStats(): Promise<DashboardStats> {
  return apiRequest<DashboardStats>('/api/events/stats');
}

export async function getCameraStatuses(): Promise<CameraStatus[]> {
  return apiRequest<CameraStatus[]>('/api/events/cameras');
}

// ---------------------------------------------------------------- robot

export async function getRobotStatus(): Promise<RobotStatus | null> {
  return apiRequest<RobotStatus | null>('/api/robot/status');
}

export async function dispatchRobot(targetTrackId: number, reason: string) {
  return apiRequest('/api/robot/dispatch', {
    method: 'POST',
    body: JSON.stringify({ target_track_id: targetTrackId, reason }),
  });
}

// ---------------------------------------------------------------- admin

function adminPath(path: string) {
  return `/api/admin${path}`;
}

export async function getInvigilators(includeInactive = true): Promise<Invigilator[]> {
  return apiRequest<Invigilator[]>(
    `${adminPath('/invigilators')}?include_inactive=${includeInactive}`
  );
}

export async function createInvigilator(payload: {
  username: string;
  password: string;
  full_name?: string;
  email?: string;
  assigned_room_id?: number | null;
}): Promise<Invigilator> {
  return apiRequest<Invigilator>(adminPath('/invigilators'), {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function updateInvigilator(
  id: number,
  payload: {
    full_name?: string;
    email?: string;
    is_active?: boolean;
    assigned_room_id?: number | null;
    password?: string;
  }
): Promise<Invigilator> {
  return apiRequest<Invigilator>(adminPath(`/invigilators/${id}`), {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export async function getRooms(): Promise<ExamRoom[]> {
  return apiRequest<ExamRoom[]>(adminPath('/rooms'));
}

export async function createRoom(payload: {
  room_code: string;
  name: string;
  building?: string;
}): Promise<ExamRoom> {
  return apiRequest<ExamRoom>(adminPath('/rooms'), {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}
