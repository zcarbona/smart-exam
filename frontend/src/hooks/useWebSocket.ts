'use client';
import { useEffect, useRef, useState, useCallback } from 'react';
import { StudentTrack, ViolationEvent } from '@/lib/types';

interface WSMessage {
  type: string;
  data?: any;
}

export function useWebSocket(url: string) {
  const [isConnected, setIsConnected] = useState(false);
  const [liveCount, setLiveCount] = useState(0);
  const [fps, setFps] = useState(0);
  const [tracks, setTracks] = useState<Record<number, StudentTrack>>({});
  const [recentEvents, setRecentEvents] = useState<ViolationEvent[]>([]);
  const [examStatus, setExamStatus] = useState<"running" | "paused">("running");
  const [pauseReason, setPauseReason] = useState<string | null>(null);
  const [countAlert, setCountAlert] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const connect = useCallback(() => {
    if (typeof window === 'undefined') return;

    try {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        setIsConnected(true);
      };

      ws.onclose = () => {
        setIsConnected(false);
        reconnectTimeoutRef.current = setTimeout(connect, 2000);
      };

      ws.onerror = () => {
        ws.close();
      };

      ws.onmessage = (event) => {
        try {
          const msg: WSMessage = JSON.parse(event.data);

          if (msg.type === 'violation_event' && msg.data) {
            const ev: ViolationEvent = msg.data;
            setRecentEvents((prev) => [ev, ...prev].slice(0, 30));

            if (ev.track_id !== undefined) {
              setTracks((prev) => {
                const existing = prev[ev.track_id!] || {
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
                    ...existing,
                    student_name: ev.student_name || existing.student_name,
                    score: ev.total_score ?? existing.score + ev.points,
                    is_suspicious: ev.is_suspicious ?? (existing.score + ev.points >= 10),
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
                  updated[t.track_id] = {
                    ...(updated[t.track_id] || {}),
                    ...t,
                  };
                }
                return updated;
              });
            }
          }

          if (msg.type === 'exam_state' && msg.data) {
            setExamStatus(msg.data.status);
            setPauseReason(msg.data.reason || null);
          }
        } catch (e) {
          console.error('[WebSocket] Failed to parse message:', e);
        }
      };
    } catch (e) {
      console.error('[WebSocket] Init error:', e);
    }
  }, [url]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      if (wsRef.current) wsRef.current.close();
    };
  }, [connect]);

  return {
    isConnected,
    liveCount,
    fps,
    tracks: Object.values(tracks),
    recentEvents,
    examStatus,
    pauseReason,
    countAlert,
    setCountAlert,
  };
}
