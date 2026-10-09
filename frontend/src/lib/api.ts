import { User } from './types';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

let refreshHandler: (() => Promise<string | null>) | null = null;

export function registerAuthRefresh(handler: () => Promise<string | null>) {
  refreshHandler = handler;
}

export async function apiRequest(endpoint: string, options: RequestInit = {}) {
  const token = typeof window !== 'undefined' ? localStorage.getItem('smartexam_token') : null;
  const headers = new Headers(options.headers || {});

  if (token && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }

  let response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers,
  });

  // Automatic token refresh on 401 if refresh handler is registered
  if (response.status === 401 && refreshHandler) {
    const newToken = await refreshHandler();
    if (newToken) {
      headers.set('Authorization', `Bearer ${newToken}`);
      response = await fetch(`${API_BASE}${endpoint}`, {
        ...options,
        headers,
      });
    }
  }

  return response;
}

export async function login(username: string, password: string) {
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to login');
  }
  return res.json();
}

export async function refreshToken(refreshTokenStr: string) {
  const res = await fetch(`${API_BASE}/api/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshTokenStr }),
  });
  if (!res.ok) {
    throw new Error('Refresh token expired or invalid');
  }
  return res.json();
}

export async function getCurrentUser(token?: string): Promise<User> {
  const headers: HeadersInit = token ? { Authorization: `Bearer ${token}` } : {};
  const res = await apiRequest('/api/auth/me', { headers });
  if (!res.ok) throw new Error('Failed to load user profile');
  return res.json();
}

export async function getExamStatus() {
  const res = await apiRequest('/api/exams/status');
  if (!res.ok) throw new Error('Failed to load exam status');
  return res.json();
}

export async function pauseExam(reason = 'Proctor paused exam') {
  const res = await apiRequest(`/api/exams/pause?reason=${encodeURIComponent(reason)}`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error('Failed to pause exam');
  return res.json();
}

export async function resumeExam() {
  const res = await apiRequest('/api/exams/resume', { method: 'POST' });
  if (!res.ok) throw new Error('Failed to resume exam');
  return res.json();
}

export async function getStudents() {
  const res = await apiRequest('/api/exams/students');
  if (!res.ok) throw new Error('Failed to load students');
  return res.json();
}

export async function assignStudent(trackId: number, studentCollegeId: string, studentName: string) {
  const res = await apiRequest('/api/exams/assign-student', {
    method: 'POST',
    body: JSON.stringify({
      track_id: trackId,
      student_college_id: studentCollegeId,
      student_name: studentName,
    }),
  });
  if (!res.ok) throw new Error('Failed to assign student');
  return res.json();
}

export async function getRobotStatus() {
  const res = await apiRequest('/api/robot/status');
  if (!res.ok) throw new Error('Failed to load robot status');
  return res.json();
}

export async function dispatchRobot(targetTrackId: number, reason: string) {
  const res = await apiRequest('/api/robot/dispatch', {
    method: 'POST',
    body: JSON.stringify({ target_track_id: targetTrackId, reason }),
  });
  if (!res.ok) throw new Error('Failed to dispatch robot');
  return res.json();
}
