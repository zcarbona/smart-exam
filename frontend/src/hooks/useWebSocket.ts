'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { StudentTrack, ViolationEvent } from '@/lib/types';
import { getAccessToken } from '@/lib/api';

interface WSMessage {
  type: string;
  data?: any;
}

const RECONNECT_DELAY_MS = 2000;
const MAX_RECONNECT_DELAY_MS = 30000;
const MAX_EVENTS = 100;

function wsBaseUrl(): string {
  const configured = process.env.NEXT_PUBLIC_WS_URL;
  if (configured) return configured;
  // Derive from the API base so the two can never drift apart.
  const apiBase = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
  return apiBase.replace(/^http/, 'ws') + '/ws/dashboard';
}

export function useWebSocket(roomId?: number | null) {
  const [isConnected, setIsConnected] = useState(false);
  const [liveCount, setLiveCount] = useState(0);
  const [fps, setFps] = useState(0);
  const [tracks, setTracks] = useState<Record<number, StudentTrack>>({});
  const [recentEvents, setRecentEvents] = useState<ViolationEvent[]>([]);
  const [examStatus, setExamStatus] = useState<'running' | 'paused'>('running');
  const [pauseReason, setPauseReason] = useState<string | null>(null);
  const [connectionError, setConnectionError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttemptRef = useRef(0);
  const closedByUsRef = useRef(false);
  const seenEventIdsRef = useRef<Set<number>>(new Set());

  // Refetch a full snapshot after (re)connecting. Streaming only carries what
  // happens while the socket is open, so anything emitted during a disconnect
  // would otherwise be lost permanently.
  const onReconnectRef = useRef<(() => void) | null>(null);
  const registerReconnectSnapshot = useCallback((handler: () => void) => {
    onReconnectRef.current = handler;
  }, []);

  const connect = useCallback(() => {
    if (typeof window === 'undefined') return;

    const token = getAccessToken();
    if (!token) {
      // No session: do not retry blindly. The auth gate handles redirect.
      setIsConnected(false);
      setConnectionError('Not authenticated');
      return;
    }

    const params = new URLSearchParams({ token });
    if (roomId !== undefined && roomId !== null) params.set('room_id', String(roomId));

    let ws: WebSocket;
    try {
      ws = new WebSocket(`${wsBaseUrl()}?${params.toString()}`);
    } catch {
      scheduleReconnect();
      return;
    }

    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
      setConnectionError(null);
      reconnectAttemptRef.current = 0;
      // Pull a fresh snapshot so nothing that happened while we were away is
      // silently dropped.
      onReconnectRef.current?.();
    };

    ws.onclose = (event) => {
      setIsConnected(false);
      if (closedByUsRef.current) return;

      if (event.code === 4401 || event.code === 4403) {
        // Rejected by the server for auth/authorization reasons. Reconnecting
        // with the same token cannot succeed, so stop.
        setConnectionError(
          event.code === 4403
            ? 'Session revoked or account deactivated'
            : 'Session expired. Please sign in again.'
        );
        return;
      }
      scheduleReconnect();
    };

    ws.onerror = () => {
      // The close handler drives reconnection.
    };

    ws.onmessage = (event) => {
      try {
        const msg: WSMessage = JSON.parse(event.data);

        if (msg.type === 'violation_event' && msg.data) {
          const ev = msg.data as ViolationEvent;

          // Deduplicate: the backend may replay an event after a reconnect
          // snapshot has already been fetched.
          if (ev.id !== undefined) {
            if (seenEventIdsRef.current.has(ev.id)) return;
            seenEventIdsRef.current.add(ev.id);
            if (seenEventIdsRef.current.size > 500) {
              seenEventIdsRef.current = new Set(
                Array.from(seenEventIdsRef.current).slice(-250)
              );
            }
          }

          setRecentEvents((prev) => [ev, ...prev].slice(0, MAX_EVENTS));

          if (ev.track_id !== undefined) {
            setTracks((prev) => {
              const existing = prev[ev.track_id!];
              const base: StudentTrack =
                existing || {
                  track_id: ev.track_id!,
                  score: 0,
                  is_suspicious: false,
                  presence_state: 'present',
                  head_yaw: 0,
                  head_pitch: 0,
                  gaze_direction: 'Eyes Center',
                  zone_status: 'safe',
                };
              return {
                ...prev,
                [ev.track_id!]: {
                  ...base,
                  student_name: ev.student_name || base.student_name,
                  student_college_id: ev.student_college_id || base.student_college_id,
                  score: ev.total_score ?? base.score + ev.points,
                  is_suspicious: ev.is_suspicious ?? (base.score + ev.points >= 10),
                },
              };
            });
          }
        }

        if (msg.type === 'status_sync' && msg.data) {
          setLiveCount(msg.data.live_student_count || 0);
          setFps(msg.data.fps || 0);

            if (Array.isArray(msg.data.tracks)) {
              setTracks((prev) => {
                const updated = { ...prev };
                for (const t of msg.data.tracks) {
                  const base = updated[t.track_id] || ({} as StudentTrack);
                  updated[t.track_id] = { ...base, ...t } as StudentTrack;
                }
                return updated;
              });
            }
        }

        if (msg.type === 'exam_state' && msg.data) {
          setExamStatus(msg.data.status);
          setPauseReason(msg.data.reason || null);
        }

        if (msg.type === 'student_assigned' && msg.data) {
          setTracks((prev) => {
            const existing = prev[msg.data.track_id];
            if (!existing) return prev;
            return {
              ...prev,
              [msg.data.track_id]: {
                ...existing,
                student_name: msg.data.student_name,
                student_college_id: msg.data.student_college_id,
              },
            };
          });
        }
      } catch (e) {
        console.error('[WebSocket] Failed to parse message:', e);
      }
    };

    function scheduleReconnect() {
      if (closedByUsRef.current) return;
      const attempt = reconnectAttemptRef.current;
      const delay = Math.min(RECONNECT_DELAY_MS * 2 ** attempt, MAX_RECONNECT_DELAY_MS);
      reconnectAttemptRef.current = attempt + 1;
      reconnectTimeoutRef.current = setTimeout(() => connect(), delay);
    }
  }, [roomId]);

  useEffect(() => {
    closedByUsRef.current = false;
    connect();
    return () => {
      closedByUsRef.current = true;
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return {
    isConnected,
    connectionError,
    liveCount,
    fps,
    tracks: Object.values(tracks),
    recentEvents,
    examStatus,
    pauseReason,
    registerReconnectSnapshot,
  };
}
