'use client';
import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { useWebSocket } from '@/hooks/useWebSocket';
import { pauseExam, resumeExam, assignStudent, dispatchRobot } from '@/lib/api';
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
  ExternalLink,
} from 'lucide-react';

export default function DashboardPage() {
  const { user, loading, logout } = useAuth();
  const router = useRouter();

  const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000/ws/dashboard';
  const { isConnected, liveCount, fps, tracks, recentEvents, examStatus, pauseReason } = useWebSocket(WS_URL);

  const [modalImage, setModalImage] = useState<string | null>(null);
  const [assignTrackId, setAssignTrackId] = useState<number>(0);
  const [assignCollegeId, setAssignCollegeId] = useState('');
  const [assignName, setAssignName] = useState('');
  const [assignSuccess, setAssignSuccess] = useState(false);

  useEffect(() => {
    if (!loading && !user) {
      router.push('/login');
    }
  }, [user, loading, router]);

  const handleToggleExam = async () => {
    try {
      if (examStatus === 'running') {
        await pauseExam('Proctor manual toggle');
      } else {
        await resumeExam();
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleAssignStudent = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!assignCollegeId || !assignName) return;
    try {
      await assignStudent(assignTrackId, assignCollegeId, assignName);
      setAssignSuccess(true);
      setTimeout(() => setAssignSuccess(false), 3000);
      setAssignCollegeId('');
      setAssignName('');
    } catch (e) {
      console.error(e);
    }
  };

  const handleDispatchRobot = async (trackId: number) => {
    try {
      await dispatchRobot(trackId, `Proctor dispatch to inspect Student ${trackId}`);
      alert(`Robot ROBOT-01 dispatched to Student ${trackId}!`);
    } catch (e) {
      console.error(e);
    }
  };

  if (loading || !user) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-950 text-slate-400 text-sm">
        Verifying proctor credentials...
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 p-4 md:p-6">
      {/* Top Header */}
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800 pb-4 mb-6">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-600/20 text-indigo-400 border border-indigo-500/30">
            <ShieldAlert className="h-6 w-6" />
          </div>
          <div>
            <h1 className="text-lg font-bold tracking-tight text-white">Smart Exam Proctoring</h1>
            <p className="text-xs text-slate-400">Live AI Room Monitoring Station</p>
          </div>
        </div>

        <div className="flex items-center gap-3 flex-wrap">
          {/* Connection status */}
          <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold ${
            isConnected ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-red-500/10 text-red-400 border border-red-500/20'
          }`}>
            {isConnected ? <Wifi className="h-3.5 w-3.5" /> : <WifiOff className="h-3.5 w-3.5" />}
            <span>{isConnected ? 'WebSocket Live' : 'Disconnected'}</span>
          </div>

          {/* FPS Badge */}
          <div className="px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-xs font-semibold text-slate-300">
            FPS: <span className={fps >= 15 ? 'text-emerald-400' : 'text-amber-400'}>{fps}</span>
          </div>

          {/* Student Counter */}
          <div className="px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-xs font-semibold text-sky-400">
            Students: <span>{liveCount}</span>
          </div>

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
            onClick={logout}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-xs font-medium text-slate-400 hover:text-white transition-all cursor-pointer"
          >
            <LogOut className="h-3.5 w-3.5" />
            <span>Sign Out</span>
          </button>
        </div>
      </header>

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

      {/* Main Grid: Left (Students & Assign Form), Right (Live Feed & Events) */}
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
              <p className="mt-2 text-xs text-emerald-400">✓ Student details updated successfully!</p>
            )}
          </div>

          {/* Student Cards Grid */}
          <div>
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-3">
              Tracked Students ({tracks.length})
            </h2>

            {tracks.length === 0 ? (
              <div className="rounded-xl border border-slate-800 bg-slate-900/30 p-8 text-center text-xs text-slate-500">
                Waiting for AI Pipeline to detect students in room...
              </div>
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
                            {student.student_name || `Student ${student.track_id}`}
                          </div>
                          <div className="text-[11px] text-slate-400">
                            Track: {student.track_id} {student.student_college_id ? `| ID: ${student.student_college_id}` : ''}
                          </div>
                          <span
                            className={`inline-block mt-2 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase ${
                              student.presence_state === 'present'
                                ? 'bg-emerald-500/10 text-emerald-400'
                                : 'bg-red-500/10 text-red-400'
                            }`}
                          >
                            {student.presence_state.replace('_', ' ')}
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
                            {student.gaze_direction}
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
                            {student.zone_status.toUpperCase()}
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

        {/* Right Column: Prepared Robot Manager & Real-Time Event Log */}
        <div className="space-y-6">
          {/* Robot Manager Widget (Prepared as requested in diagram) */}
          <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-2">
                <Bot className="h-4 w-4 text-indigo-400" />
                Robot Manager (Standby)
              </h2>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                MQTT Standby
              </span>
            </div>
            <div className="rounded-lg bg-slate-800/50 p-3 text-xs space-y-1.5">
              <div className="flex justify-between">
                <span className="text-slate-400">Assigned Unit:</span>
                <span className="font-semibold text-white">ROBOT-01 (LiDAR / YOLO)</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Status:</span>
                <span className="font-semibold text-emerald-400">Idle / Patrolling Room</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Battery Level:</span>
                <span className="font-semibold text-white">96.5%</span>
              </div>
            </div>
          </div>

          {/* Live Violation Events Feed */}
          <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-3 flex items-center gap-2">
              <ShieldAlert className="h-4 w-4 text-red-400" />
              Live Violation Feed ({recentEvents.length})
            </h2>

            <div className="space-y-2.5 max-h-[480px] overflow-y-auto pr-1">
              {recentEvents.length === 0 ? (
                <div className="p-6 text-center text-xs text-slate-500">No violation events recorded yet.</div>
              ) : (
                recentEvents.map((ev, idx) => (
                  <div
                    key={idx}
                    className="flex items-center gap-3 rounded-lg border border-slate-800 bg-slate-900/90 p-2.5 hover:border-slate-700 transition-all"
                  >
                    {ev.evidence_url ? (
                      <img
                        src={`http://localhost:8000${ev.evidence_url}`}
                        alt="Evidence"
                        onClick={() => setModalImage(`http://localhost:8000${ev.evidence_url}`)}
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
                        Track {ev.track_id} • {ev.timestamp}
                      </div>
                    </div>

                    <div className="text-xs font-black text-red-400 shrink-0">
                      +{ev.points}
                    </div>
                  </div>
                ))
              )}
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
  );
}
