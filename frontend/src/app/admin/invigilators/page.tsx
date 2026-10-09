'use client';
import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import {
  createInvigilator,
  createRoom,
  getInvigilators,
  getRooms,
  updateInvigilator,
} from '@/lib/api';
import type { ExamRoom, Invigilator } from '@/lib/types';
import { EmptyState, ErrorState, RequireAdmin } from '@/components/Guards';
import {
  ShieldAlert,
  LogOut,
  ArrowLeft,
  UserPlus,
  Users,
  RefreshCw,
  CheckCircle2,
  XCircle,
  Building2,
} from 'lucide-react';

const EMPTY_FORM = {
  username: '',
  password: '',
  full_name: '',
  email: '',
  assigned_room_id: '',
};

export default function InvigilatorsAdminPage() {
  const { user, logout } = useAuth();
  const router = useRouter();

  const [invigilators, setInvigilators] = useState<Invigilator[] | null>(null);
  const [rooms, setRooms] = useState<ExamRoom[]>([]);
  const [listError, setListError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ ...EMPTY_FORM });

  const [roomForm, setRoomForm] = useState({ room_code: '', name: '', building: '' });
  const [roomError, setRoomError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setListError(null);
    try {
      const [list, roomList] = await Promise.all([
        getInvigilators(true),
        getRooms().catch(() => [] as ExamRoom[]),
      ]);
      setInvigilators(list);
      setRooms(roomList);
    } catch (err: any) {
      setInvigilators(null);
      setListError(err?.message || 'Failed to load accounts');
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    setSuccess(null);
    setBusy(true);

    try {
      await createInvigilator({
        username: form.username.trim(),
        password: form.password,
        full_name: form.full_name.trim() || undefined,
        email: form.email.trim() || undefined,
        // The role is never sent: the server assigns `invigilator` itself.
        assigned_room_id: form.assigned_room_id ? Number(form.assigned_room_id) : null,
      });
      setSuccess(`Invigilator "${form.username.trim()}" created successfully.`);
      setForm({ ...EMPTY_FORM });
      // Re-read from the database so the list reflects what was actually stored.
      await load();
    } catch (err: any) {
      setFormError(err?.message || 'Failed to create invigilator');
    } finally {
      setBusy(false);
    }
  };

  const handleToggleActive = async (inv: Invigilator) => {
    setListError(null);
    setSuccess(null);
    try {
      await updateInvigilator(inv.id, { is_active: !inv.is_active });
      await load();
      setSuccess(`${inv.username} is now ${inv.is_active ? 'deactivated' : 'active'}.`);
    } catch (err: any) {
      setListError(err?.message || 'Failed to update account');
    }
  };

  const handleResetPassword = async (inv: Invigilator) => {
    const password = window.prompt(`New password for ${inv.username} (min 12 chars):`);
    if (!password) return;
    setListError(null);
    setSuccess(null);
    try {
      await updateInvigilator(inv.id, { password });
      setSuccess(`Password reset for ${inv.username}.`);
    } catch (err: any) {
      setListError(err?.message || 'Failed to reset password');
    }
  };

  const handleCreateRoom = async (e: React.FormEvent) => {
    e.preventDefault();
    setRoomError(null);
    setSuccess(null);
    try {
      await createRoom({
        room_code: roomForm.room_code.trim(),
        name: roomForm.name.trim(),
        building: roomForm.building.trim() || undefined,
      });
      setRoomForm({ room_code: '', name: '', building: '' });
      setSuccess('Exam room created.');
      load();
    } catch (err: any) {
      setRoomError(err?.message || 'Failed to create room');
    }
  };

  return (
    <RequireAdmin>
      <div className="min-h-screen bg-slate-950 text-slate-100 p-4 md:p-6">
        <header className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800 pb-4 mb-6">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-600/20 text-indigo-400 border border-indigo-500/30">
              <ShieldAlert className="h-6 w-6" />
            </div>
            <div>
              <h1 className="text-lg font-bold tracking-tight text-white">Invigilator Management</h1>
              <p className="text-xs text-slate-400">Admin console — signed in as {user?.username}</p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => router.push('/dashboard')}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-xs font-medium text-slate-400 hover:text-white transition-all cursor-pointer"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              <span>Dashboard</span>
            </button>
            <button
              onClick={() => logout()}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-xs font-medium text-slate-400 hover:text-white transition-all cursor-pointer"
            >
              <LogOut className="h-3.5 w-3.5" />
              <span>Sign Out</span>
            </button>
          </div>
        </header>

        {success && (
          <div className="mb-6 flex items-center gap-2 rounded-xl border border-emerald-500/20 bg-emerald-500/10 p-3 text-xs text-emerald-400">
            <CheckCircle2 className="h-4 w-4 shrink-0" />
            <span>{success}</span>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Create form */}
          <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-3 flex items-center gap-2">
              <UserPlus className="h-4 w-4 text-indigo-400" />
              Add Invigilator
            </h2>

            <form onSubmit={handleCreate} className="space-y-3">
              <div>
                <label className="block text-[11px] text-slate-400 mb-1">Username</label>
                <input
                  required
                  value={form.username}
                  onChange={(e) => setForm({ ...form, username: e.target.value })}
                  className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-white focus:outline-none"
                  placeholder="e.g. invigilator01"
                />
              </div>
              <div>
                <label className="block text-[11px] text-slate-400 mb-1">
                  Temporary Password (min 12 chars)
                </label>
                <input
                  required
                  type="password"
                  value={form.password}
                  onChange={(e) => setForm({ ...form, password: e.target.value })}
                  className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-white focus:outline-none"
                  placeholder="••••••••••••"
                />
              </div>
              <div>
                <label className="block text-[11px] text-slate-400 mb-1">Full Name</label>
                <input
                  value={form.full_name}
                  onChange={(e) => setForm({ ...form, full_name: e.target.value })}
                  className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-white focus:outline-none"
                  placeholder="Optional"
                />
              </div>
              <div>
                <label className="block text-[11px] text-slate-400 mb-1">Email</label>
                <input
                  type="email"
                  value={form.email}
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                  className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-white focus:outline-none"
                  placeholder="Optional"
                />
              </div>
              <div>
                <label className="block text-[11px] text-slate-400 mb-1">Assigned Room</label>
                <select
                  value={form.assigned_room_id}
                  onChange={(e) => setForm({ ...form, assigned_room_id: e.target.value })}
                  className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-white focus:outline-none"
                >
                  <option value="">No room restriction</option>
                  {rooms.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.name} ({r.room_code})
                    </option>
                  ))}
                </select>
              </div>

              <div className="rounded-lg border border-slate-800 bg-slate-800/40 p-2 text-[10px] text-slate-500">
                New accounts are created with the <strong className="text-slate-300">invigilator</strong> role
                by the server. Role cannot be selected here.
              </div>

              {formError && <p className="text-xs text-red-400">{formError}</p>}

              <button
                type="submit"
                disabled={busy}
                className="w-full rounded-lg bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-500 disabled:opacity-50 cursor-pointer"
              >
                {busy ? 'Creating...' : 'Create Invigilator'}
              </button>
            </form>
          </div>

          {/* Account list */}
          <div className="lg:col-span-2 rounded-xl border border-slate-800 bg-slate-900/60 p-4">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-2">
                <Users className="h-4 w-4 text-indigo-400" />
                Invigilator Accounts ({invigilators?.length ?? 0})
              </h2>
              <button
                onClick={load}
                className="flex items-center gap-1.5 rounded-lg bg-slate-800 px-2.5 py-1 text-[11px] text-slate-300 hover:bg-slate-700 cursor-pointer"
              >
                <RefreshCw className="h-3 w-3" />
                Refresh
              </button>
            </div>

            {listError ? (
              <ErrorState message={listError} />
            ) : invigilators === null ? (
              <div className="space-y-2">
                {Array.from({ length: 4 }).map((_, i) => (
                  <div key={i} className="h-14 animate-pulse rounded-lg border border-slate-800 bg-slate-900/40" />
                ))}
              </div>
            ) : invigilators.length === 0 ? (
              <EmptyState
                icon={Users}
                title="No invigilator accounts yet"
                hint="Create the first invigilator using the form."
              />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-left text-slate-500 border-b border-slate-800">
                      <th className="pb-2 font-semibold">Username</th>
                      <th className="pb-2 font-semibold">Name</th>
                      <th className="pb-2 font-semibold">Room</th>
                      <th className="pb-2 font-semibold">Status</th>
                      <th className="pb-2 font-semibold text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {invigilators.map((inv) => (
                      <tr key={inv.id} className="border-b border-slate-800/60">
                        <td className="py-2.5 text-white font-semibold">{inv.username}</td>
                        <td className="py-2.5 text-slate-400">{inv.full_name || '—'}</td>
                        <td className="py-2.5 text-slate-400">
                          {inv.assigned_room_id
                            ? rooms.find((r) => r.id === inv.assigned_room_id)?.name || `#${inv.assigned_room_id}`
                            : 'All rooms'}
                        </td>
                        <td className="py-2.5">
                          <span
                            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold ${
                              inv.is_active
                                ? 'bg-emerald-500/10 text-emerald-400'
                                : 'bg-red-500/10 text-red-400'
                            }`}
                          >
                            {inv.is_active ? (
                              <CheckCircle2 className="h-3 w-3" />
                            ) : (
                              <XCircle className="h-3 w-3" />
                            )}
                            {inv.is_active ? 'Active' : 'Deactivated'}
                          </span>
                        </td>
                        <td className="py-2.5 text-right space-x-2">
                          <button
                            onClick={() => handleToggleActive(inv)}
                            className="rounded bg-slate-800 px-2 py-1 text-[10px] text-slate-300 hover:bg-slate-700 cursor-pointer"
                          >
                            {inv.is_active ? 'Deactivate' : 'Activate'}
                          </button>
                          <button
                            onClick={() => handleResetPassword(inv)}
                            className="rounded bg-slate-800 px-2 py-1 text-[10px] text-slate-300 hover:bg-slate-700 cursor-pointer"
                          >
                            Reset Password
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Rooms */}
          <div className="lg:col-span-3 rounded-xl border border-slate-800 bg-slate-900/60 p-4">
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-3 flex items-center gap-2">
              <Building2 className="h-4 w-4 text-indigo-400" />
              Exam Rooms
            </h2>

            <form onSubmit={handleCreateRoom} className="flex flex-wrap gap-3 items-end mb-4">
              <div>
                <label className="block text-[11px] text-slate-400 mb-1">Room Code</label>
                <input
                  required
                  value={roomForm.room_code}
                  onChange={(e) => setRoomForm({ ...roomForm, room_code: e.target.value })}
                  className="w-36 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-white focus:outline-none"
                  placeholder="HALL-101"
                />
              </div>
              <div>
                <label className="block text-[11px] text-slate-400 mb-1">Name</label>
                <input
                  required
                  value={roomForm.name}
                  onChange={(e) => setRoomForm({ ...roomForm, name: e.target.value })}
                  className="w-48 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-white focus:outline-none"
                  placeholder="Hall 101"
                />
              </div>
              <div>
                <label className="block text-[11px] text-slate-400 mb-1">Building</label>
                <input
                  value={roomForm.building}
                  onChange={(e) => setRoomForm({ ...roomForm, building: e.target.value })}
                  className="w-44 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-white focus:outline-none"
                  placeholder="Optional"
                />
              </div>
              <button
                type="submit"
                className="rounded-lg bg-indigo-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-indigo-500 cursor-pointer"
              >
                Add Room
              </button>
            </form>

            {roomError && <p className="mb-3 text-xs text-red-400">{roomError}</p>}

            {rooms.length === 0 ? (
              <EmptyState icon={Building2} title="No exam rooms configured" />
            ) : (
              <div className="flex flex-wrap gap-2">
                {rooms.map((r) => (
                  <span
                    key={r.id}
                    className="rounded-full border border-slate-800 bg-slate-900/60 px-3 py-1 text-[11px] text-slate-300"
                  >
                    {r.name} <span className="text-slate-500">({r.room_code})</span>
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </RequireAdmin>
  );
}
