'use client';
import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { useWebSocket } from '@/hooks/useWebSocket';
import {
  assignStudent,
  dispatchRobot,
  getCameraStatuses,
  getDashboardStats,
  getExamStatus,
  getRecentEvents,
  getRobotStatus,
  pauseExam,
  resumeExam,
  API_BASE,
} from '@/lib/api';
import type {
  CameraStatus,
  DashboardStats as DashboardStatsType,
  ExamSession,
  RobotStatus,
  ViolationEvent,
} from '@/lib/types';
import {
  EmptyState,
  ErrorState,
  RequireAuth,
} from '@/components/Guards';
import {
  ShieldAlert,
  Play,
  Pause,
  LogOut,
  Wifi,
  WifiOff,
  UserCheck,
  Eye,
  Camera,
  Bot,
  AlertTriangle,
  X,
  Users,
  ServerCog,
  Activity,
} from 'lucide-react';

function StatCard({
  label,
  value,
  hint,
  tone = 'default',
  icon: Icon,
}: {
  label: string;
  value: string | number;
  hint?: string;
  tone?: 'default' | 'danger' | 'success' | 'muted';
  icon?: typeof ShieldAlert;
}) {
  const toneClass =
    tone === 'danger'
      ? 'text-red-400'
      : tone === 'success'
      ? 'text-emerald-400'
      : tone === 'muted'
      ? 'text-slate-500'
      : 'text-white';

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3">
      <div className="flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-wider text-slate-400">{label}</span>
        {Icon && <Icon className="h-3.5 w-3.5 text-slate-600" />}
      </div>
      <div className={`mt-1 text-xl font-black ${toneClass}`}>{value}</div>
      {hint && <div className="text-[10px] text-slate-500">{hint}</div>}
    </div>
  );
}

function CameraBadge({ status }: { status: CameraStatus['status'] }) {
  const map = {
    online: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
    offline: 'bg-red-500/10 text-red-400 border-red-500/20',
    unknown: 'bg-slate-500/10 text-slate-400 border-slate-600/20',
  } as const;
  return (
    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${map[status]}`}>
      {status.toUpperCase()}
    </span>
  );
}

export default function DashboardPage() {
  const { user, loading, logout } = useAuth();
  const router = useRouter();

  const { isConnected, connectionError, liveCount, fps, tracks, recentEvents, examStatus, pauseReason, registerReconnectSnapshot } =
    useWebSocket(user?.assigned_room_id ?? null);

  const [modalImage, setModalImage] = useState<string | null>(null);
  const [assignTrackId, setAssignTrackId] = useState<number>(0);
  const [assignCollegeId, setAssignCollegeId] = useState('');
  const [assignName, setAssignName] = useState('');
  const [assignSuccess, setAssignSuccess] = useState(false);
  const [assignError, setAssignError] = useState<string | null>(null);

  // Everything below comes from the backend. When a request fails we show the
  // failure rather than falling back to sample data.
  const [exam, setExam] = useState<ExamSession | null>(null);
  const [examError, setExamError] = useState<string | null>(null);
  const [robot, setRobot] = useState<RobotStatus | null>(null);
  const [robotError, setRobotError] = useState<string | null>(null);
  const [cameras, setCameras] = useState<CameraStatus[]>([]);
  const [camerasError, setCamerasError] = useState<string | null>(null);
  const [stats, setStats] = useState<DashboardStatsType | null>(null);
  const [statsError, setStatsError] = useState<string | null>(null);
  const [history, setHistory] = useState<ViolationEvent[]>([]);
  const [historyError, setHistoryError] = useState<string | null>(null);

  const loadSnapshot = useCallback(async () => {
    // REST snapshot: authoritative history plus every counter, fetched fresh
    // after each (re)connect so events emitted during a disconnect are not lost.
    const [examRes, robotRes, camRes, statsRes, eventsRes] = await Promise.allSettled([
      getExamStatus(),
      getRobotStatus(),
      getCameraStatuses(),
      getDashboardStats(),
      getRecentEvents(50),
    ]);

    if (examRes.status === 'fulfilled') {
      setExam(examRes.value);
      setExamError(null);
    } else {
      setExam(null);
      setExamError(examRes.reason?.message || 'Failed to load exam status');
    }

    if (robotRes.status === 'fulfilled') {
      setRobot(robotRes.value);
      setRobotError(null);
    } else {
      setRobot(null);
      setRobotError(robotRes.reason?.message || 'Failed to load robot status');
    }

    if (camRes.status === 'fulfilled') {
      setCameras(camRes.value);
      setCamerasError(null);
    } else {
      setCameras([]);
      setCamerasError(camRes.reason?.message || 'Failed to load camera status');
    }

    if (statsRes.status === 'fulfilled') {
      setStats(statsRes.value);
      setStatsError(null);
    } else {
      setStats(null);
      setStatsError(statsRes.reason?.message || 'Failed to load statistics');
    }

    if (eventsRes.status === 'fulfilled') {
      setHistory(eventsRes.value);
      setHistoryError(null);
    } else {
      setHistory([]);
      setHistoryError(eventsRes.reason?.message || 'Failed to load event history');
    }
  }, []);

  useEffect(() => {
    if (!loading && user) loadSnapshot();
  }, [loading, user, loadSnapshot]);

  // Pull a fresh snapshot whenever the socket (re)connects.
  useEffect(() => {
    registerReconnectSnapshot(() => {
      loadSnapshot();
    });
  }, [registerReconnectSnapshot, loadSnapshot]);

  const handleToggleExam = async () => {
    setExamError(null);
    try {
      if (examStatus === 'running') {
        await pauseExam('Proctor manual toggle');
      } else {
        await resumeExam();
      }
      setExam(await getExamStatus());
    } catch (e: any) {
      setExamError(e?.message || 'Failed to change exam state');
    }
  };

  const handleAssignStudent = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!assignCollegeId || !assignName) return;
    setAssignError(null);
    try {
      await assignStudent(assignTrackId, assignCollegeId, assignName);
      setAssignSuccess(true);
      setTimeout(() => setAssignSuccess(false), 3000);
      setAssignCollegeId('');
      setAssignName('');
    } catch (err: any) {
      setAssignSuccess(false);
      setAssignError(err?.message || 'Failed to bind student details');
    }
  };

  const handleDispatchRobot = async (trackId: number) => {
    try {
      await dispatchRobot(trackId, `Proctor dispatch to inspect Student ${trackId}`);
      const updated = await getRobotStatus();
      setRobot(updated);
    } catch (err: any) {
      setRobotError(err?.message || 'Failed to dispatch robot');
    }
  };

  // Gating is handled by <RequireAuth>: it waits for the backend to confirm the
  // identity before rendering, so nothing here runs for a signed-out visitor.

  const onlineCameras = stats?.cameras_online ?? 0;
  const totalCameras = stats?.cameras_total ?? 0;

  return (
    <RequireAuth>
    <div className="min-h-screen bg-slate-950 text-slate-100 p-4 md:p-6">
      {/* Top Header */}
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800 pb-4 mb-6">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-600/20 text-indigo-400 border border-indigo-500/30">
            <ShieldAlert className="h-6 w-6" />
          </div>
          <div>
            <h1 className="text-lg font-bold tracking-tight text-white">Smart Exam Proctoring</h1>
            <p className="text-xs text-slate-400">
              Live AI Room Monitoring Station
              {user?.assigned_room_id ? ' — scoped to your assigned room' : ''}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3 flex-wrap">
          {/* Connection status */}
          <div
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold ${
              isConnected
                ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                : 'bg-red-500/10 text-red-400 border border-red-500/20'
            }`}
          >
            {isConnected ? <Wifi className="h-3.5 w-3.5" /> : <WifiOff className="h-3.5 w-3.5" />}
            <span>{isConnected ? 'Live' : 'Disconnected'}</span>
          </div>

          {/* FPS Badge */}
          <div className="px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-xs font-semibold text-slate-300">
            FPS: <span className={fps >= 15 ? 'text-emerald-400' : 'text-amber-400'}>{fps}</span>
          </div>

          {/* Student Counter */}
          <div className="px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-xs font-semibold text-sky-400">
            Students: <span>{liveCount}</span>
          </div>

          {user?.role === 'admin' && (
            <button
              onClick={() => router.push('/admin/invigilators')}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 text-white text-xs font-bold hover:bg-indigo-500 transition-all cursor-pointer"
            >
              <UserCheck className="h-3.5 w-3.5" />
              <span>Manage Invigilators</span>
            </button>
          )}

          {/* Exam Pause / Resume */}
          <button
            onClick={handleToggleExam}
            className={`flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
              examStatus === 'running'
                ? 'bg-amber-600 text-white hover:bg-amber-500 shadow-lg shadow-amber-600/20'
                : 'bg-emerald-600 text-white hover:bg-emerald-500 shadow-lg shadow-emerald-600/20'
            }`}
          >
            {examStatus === 'running' ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
            <span>{examStatus === 'running' ? 'Pause Exam' : 'Resume Exam'}</span>
          </button>

          {/* User Logout */}
          <button
            onClick={() => logout()}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-xs font-medium text-slate-400 hover:text-white transition-all cursor-pointer"
          >
            <LogOut className="h-3.5 w-3.5" />
            <span>Sign Out</span>
          </button>
        </div>
      </header>

      {connectionError && (
        <div className="mb-6 rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-300">
          {connectionError}
        </div>
      )}

      {/* Paused alert banner */}
      {examStatus === 'paused' && (
        <div className="mb-6 flex items-center justify-between gap-4 rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 text-amber-300">
          <div className="flex items-center gap-3">
            <AlertTriangle className="h-5 w-5 shrink-0" />
            <div>
              <div className="text-sm font-bold">Exam Scoring is Paused</div>
              <div className="text-xs text-amber-300/80">{pauseReason || 'Paused by proctor.'}</div>
            </div>
          </div>
          <button
            onClick={handleToggleExam}
            className="rounded-lg bg-amber-500 px-4 py-1.5 text-xs font-bold text-slate-950 hover:bg-amber-400 cursor-pointer"
          >
            Resume Scoring
          </button>
        </div>
      )}

      {/* Dashboard statistics — every value is computed from real records */}
      <section className="mb-6">
        <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-3 flex items-center gap-2">
          <Activity className="h-4 w-4 text-indigo-400" />
          Live Statistics
        </h2>

        {statsError ? (
          <ErrorState message={statsError} />
        ) : !stats ? (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="h-20 animate-pulse rounded-xl border border-slate-800 bg-slate-900/40" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
            <StatCard label="Active Exams" value={stats.active_exams} icon={ShieldAlert} />
            <StatCard label="Paused" value={stats.paused_exams} tone="muted" />
            <StatCard label="Tracked Students" value={stats.tracked_students} icon={Users} />
            <StatCard
              label="Suspicious"
              value={stats.suspicious_students}
              tone={stats.suspicious_students > 0 ? 'danger' : 'success'}
            />
            <StatCard label="Events (Total)" value={stats.total_events} icon={Eye} />
            <StatCard label="Events (1h)" value={stats.events_last_hour} hint={`today: ${stats.events_today}`} />
            <StatCard
              label="Cameras Online"
              value={`${stats.cameras_online}/${stats.cameras_total}`}
              tone={stats.cameras_online > 0 ? 'success' : 'muted'}
              icon={Camera}
              hint={`offline: ${stats.cameras_offline} · unknown: ${stats.cameras_unknown}`}
            />
            <StatCard
              label="Robots Online"
              value={`${stats.robots_online}/${stats.robots_total}`}
              tone={stats.robots_online > 0 ? 'success' : 'muted'}
              icon={Bot}
            />
          </div>
        )}

        {stats && stats.event_type_breakdown.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {stats.event_type_breakdown.map((row) => (
              <span
                key={row.event_type}
                className="rounded-full border border-slate-800 bg-slate-900/60 px-2.5 py-1 text-[10px] text-slate-300"
              >
                {row.event_type.replace(/_/g, ' ')} · <strong className="text-white">{row.count}</strong>
              </span>
            ))}
          </div>
        )}
      </section>

      {/* Main Grid: Left (Students & Assign Form), Right (Cameras, Robot & Events) */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Students Grid & Controls (2 cols on lg) */}
        <div className="lg:col-span-2 space-y-6">
          {/* Relabel Student Form */}
          <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-3 flex items-center gap-2">
              <UserCheck className="h-4 w-4 text-indigo-400" />
              Bind Student Details (Auto-ID Relabel)
            </h2>
            <form onSubmit={handleAssignStudent} className="flex flex-wrap gap-3 items-center">
              <input
                type="number"
                placeholder="Track ID"
                min={0}
                value={assignTrackId}
                onChange={(e) => setAssignTrackId(parseInt(e.target.value) || 0)}
                className="w-24 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-white placeholder-slate-500 focus:outline-none"
              />
              <input
                type="text"
                placeholder="College ID (e.g. 2021004)"
                value={assignCollegeId}
                onChange={(e) => setAssignCollegeId(e.target.value)}
                className="flex-1 min-w-[140px] rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-white placeholder-slate-500 focus:outline-none"
              />
              <input
                type="text"
                placeholder="Full Name (e.g. Mohamed Ali)"
                value={assignName}
                onChange={(e) => setAssignName(e.target.value)}
                className="flex-1 min-w-[160px] rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-white placeholder-slate-500 focus:outline-none"
              />
              <button
                type="submit"
                className="rounded-lg bg-indigo-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-indigo-500 cursor-pointer"
              >
                Assign
              </button>
            </form>
            {assignSuccess && (
              <p className="mt-2 text-xs text-emerald-400">Student details updated successfully!</p>
            )}
            {assignError && <p className="mt-2 text-xs text-red-400">{assignError}</p>}
          </div>

          {/* Student Cards Grid */}
          <div>
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-3">
              Tracked Students ({tracks.length})
            </h2>

            {tracks.length === 0 ? (
              <EmptyState
                icon={Users}
                title="No students detected"
                hint="Waiting for the AI pipeline to detect students in the room."
              />
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {tracks.map((student) => {
                  const isSuspicious = student.score >= 10;
                  return (
                    <div
                      key={student.track_id}
                      className={`rounded-xl border p-4 transition-all ${
                        isSuspicious
                          ? 'border-red-500/50 bg-red-950/20 shadow-lg shadow-red-950/30'
                          : student.zone_status === 'warning'
                          ? 'border-amber-500/50 bg-amber-950/20'
                          : 'border-slate-800 bg-slate-900/50'
                      }`}
                    >
                      <div className="flex items-start justify-between">
                        <div>
                          <div className="font-bold text-sm text-white">
                            {student.student_name || `Track ${student.track_id}`}
                          </div>
                          <div className="text-[11px] text-slate-400">
                            Track: {student.track_id}{' '}
                            {student.student_college_id ? `| ID: ${student.student_college_id}` : ''}
                          </div>
                          <span
                            className={`inline-block mt-2 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase ${
                              student.presence_state === 'present'
                                ? 'bg-emerald-500/10 text-emerald-400'
                                : 'bg-red-500/10 text-red-400'
                            }`}
                          >
                            {(student.presence_state || 'unknown').replace(/_/g, ' ')}
                          </span>
                        </div>

                        <div className="text-right">
                          <div
                            className={`text-2xl font-black ${
                              isSuspicious ? 'text-red-400' : 'text-amber-300'
                            }`}
                          >
                            {Math.round(student.score)}
                          </div>
                          <span
                            className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-bold ${
                              isSuspicious
                                ? 'bg-red-600 text-white'
                                : 'bg-emerald-950/80 text-emerald-300'
                            }`}
                          >
                            {isSuspicious ? 'SUSPICIOUS' : 'CLEAN'}
                          </span>
                        </div>
                      </div>

                      {/* Pose & Gaze Mini Stats */}
                      <div className="grid grid-cols-3 gap-2 mt-4 text-center">
                        <div className="rounded-lg bg-slate-800/60 p-2">
                          <div className="text-[9px] uppercase tracking-wider text-slate-400">Yaw</div>
                          <div className="text-xs font-semibold text-slate-200 mt-0.5">
                            {student.head_yaw > 0 ? `+${student.head_yaw}` : student.head_yaw}°
                          </div>
                        </div>
                        <div className="rounded-lg bg-slate-800/60 p-2">
                          <div className="text-[9px] uppercase tracking-wider text-slate-400">Pitch</div>
                          <div className="text-xs font-semibold text-slate-200 mt-0.5">
                            {student.head_pitch > 0 ? `+${student.head_pitch}` : student.head_pitch}°
                          </div>
                        </div>
                        <div className="rounded-lg bg-slate-800/60 p-2">
                          <div className="text-[9px] uppercase tracking-wider text-slate-400">Gaze</div>
                          <div className="text-xs font-semibold text-slate-200 mt-0.5 truncate">
                            {student.gaze_direction || 'unknown'}
                          </div>
                        </div>
                      </div>

                      {/* Desk Zone Status & Robot Dispatch */}
                      <div className="flex items-center justify-between mt-3 pt-3 border-t border-slate-800/80 text-[11px]">
                        <span className="text-slate-400">
                          Zone:{' '}
                          <strong
                            className={
                              student.zone_status === 'violation'
                                ? 'text-red-400'
                                : student.zone_status === 'warning'
                                ? 'text-amber-400'
                                : 'text-emerald-400'
                            }
                          >
                            {(student.zone_status || 'unknown').toUpperCase()}
                          </strong>
                        </span>

                        <button
                          onClick={() => handleDispatchRobot(student.track_id)}
                          className="flex items-center gap-1 rounded bg-slate-800 hover:bg-slate-700 px-2 py-1 text-[10px] font-semibold text-indigo-300 transition-all cursor-pointer"
                        >
                          <Bot className="h-3 w-3" />
                          <span>Dispatch Robot</span>
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Cameras, Robot Manager & Event Log */}
        <div className="space-y-6">
          {/* Exam state */}
          <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-3 flex items-center gap-2">
              <ServerCog className="h-4 w-4 text-indigo-400" />
              Exam Session
            </h2>
            {examError ? (
              <ErrorState message={examError} />
            ) : !exam ? (
              <EmptyState title="No active exam session" hint="An administrator must start an exam." />
            ) : (
              <div className="rounded-lg bg-slate-800/50 p-3 text-xs space-y-1.5">
                <div className="flex justify-between">
                  <span className="text-slate-400">Title:</span>
                  <span className="font-semibold text-white">{exam.title}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Room:</span>
                  <span className="font-semibold text-white">{exam.room_name}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Status:</span>
                  <span
                    className={`font-semibold ${
                      exam.status === 'running' ? 'text-emerald-400' : 'text-amber-400'
                    }`}
                  >
                    {exam.status}
                  </span>
                </div>
              </div>
            )}
          </div>

          {/* Camera status — real connection state, never assumed */}
          <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-3 flex items-center gap-2">
              <Camera className="h-4 w-4 text-indigo-400" />
              Cameras ({onlineCameras}/{totalCameras} online)
            </h2>
            {camerasError ? (
              <ErrorState message={camerasError} />
            ) : cameras.length === 0 ? (
              <EmptyState
                icon={Camera}
                title="Camera status unavailable"
                hint="No cameras are registered for this room yet."
              />
            ) : (
              <div className="space-y-2">
                {cameras.map((cam) => (
                  <div
                    key={cam.id}
                    className="flex items-center justify-between rounded-lg bg-slate-800/50 p-2.5 text-xs"
                  >
                    <div className="min-w-0">
                      <div className="font-semibold text-white truncate">{cam.name}</div>
                      <div className="text-[10px] text-slate-500">{cam.device_code}</div>
                    </div>
                    <div className="flex flex-col items-end gap-1">
                      <CameraBadge status={cam.status} />
                      {cam.last_error && (
                        <div className="text-[9px] text-red-400/80 max-w-[140px] truncate">
                          {cam.last_error}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Robot Manager — values come from the robot record */}
          <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-3 flex items-center gap-2">
              <Bot className="h-4 w-4 text-indigo-400" />
              Robot Manager
            </h2>
            {robotError ? (
              <ErrorState message={robotError} />
            ) : !robot ? (
              <EmptyState
                icon={Bot}
                title="No robot connected"
                hint="No robot device has registered with the system."
              />
            ) : (
              <div className="rounded-lg bg-slate-800/50 p-3 text-xs space-y-1.5">
                <div className="flex justify-between">
                  <span className="text-slate-400">Device:</span>
                  <span className="font-semibold text-white">{robot.device_code}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Status:</span>
                  <span className="font-semibold text-emerald-400">{robot.status}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Battery:</span>
                  <span className="font-semibold text-white">{robot.battery_level}%</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Zone:</span>
                  <span className="font-semibold text-white">{robot.current_zone}</span>
                </div>
              </div>
            )}
          </div>

          {/* Violation Events Feed */}
          <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-3 flex items-center gap-2">
              <ShieldAlert className="h-4 w-4 text-red-400" />
              Violation Events ({history.length + recentEvents.length})
            </h2>

            {historyError && <ErrorState message={historyError} />}

            <div className="space-y-2.5 max-h-[480px] overflow-y-auto pr-1 mt-2">
              {(() => {
                // Prefer the REST snapshot, then append anything streamed in
                // since, keyed by id so nothing is shown twice.
                const merged = [...history];
                const seen = new Set(merged.map((e) => e.id));
                for (const ev of recentEvents) {
                  if (!seen.has(ev.id)) {
                    merged.unshift(ev);
                    seen.add(ev.id);
                  }
                }
                const ordered = merged.sort(
                  (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
                );

                if (ordered.length === 0) {
                  return (
                    <EmptyState
                      icon={ShieldAlert}
                      title="No events available"
                      hint="No AI detection events have been recorded yet."
                    />
                  );
                }

                return ordered.map((ev) => (
                  <div
                    key={ev.id}
                    className="flex items-center gap-3 rounded-lg border border-slate-800 bg-slate-900/90 p-2.5 hover:border-slate-700 transition-all"
                  >
                    {ev.evidence_url ? (
                      <img
                        src={`${API_BASE}${ev.evidence_url}`}
                        alt="Evidence"
                        onClick={() => setModalImage(`${API_BASE}${ev.evidence_url}`)}
                        className="h-10 w-14 rounded object-cover cursor-pointer hover:opacity-80 border border-slate-700 shrink-0"
                      />
                    ) : (
                      <div className="flex h-10 w-14 items-center justify-center rounded bg-slate-800 text-slate-600 shrink-0">
                        <Camera className="h-4 w-4" />
                      </div>
                    )}

                    <div className="flex-1 min-w-0">
                      <div className="text-xs font-semibold text-white truncate">
                        {ev.event_type.replace(/_/g, ' ').toUpperCase()}
                      </div>
                      <div className="text-[10px] text-slate-400">
                        {ev.student_name || 'Unknown'} · Track {ev.track_id} · {ev.timestamp}
                      </div>
                    </div>

                    <div className="text-xs font-black text-red-400 shrink-0">+{ev.points}</div>
                  </div>
                ));
              })()}
            </div>
          </div>
        </div>
      </div>

      {/* Evidence Snapshot Modal */}
      {modalImage && (
        <div
          onClick={() => setModalImage(null)}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 p-4 backdrop-blur-sm cursor-pointer"
        >
          <div className="relative max-w-4xl max-h-[90vh] overflow-hidden rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl">
            <button
              onClick={() => setModalImage(null)}
              className="absolute top-3 right-3 rounded-full bg-slate-800/80 p-2 text-slate-300 hover:text-white"
            >
              <X className="h-5 w-5" />
            </button>
            <img src={modalImage} alt="Violation Evidence" className="w-full h-auto object-contain max-h-[85vh]" />
          </div>
        </div>
      )}
    </div>
    </RequireAuth>
  );
}
