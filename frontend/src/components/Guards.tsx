'use client';
import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { ShieldAlert, Lock, Loader2 } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';

/**
 * Gate for authenticated monitoring pages.
 *
 * This waits for the server to confirm the identity rather than trusting
 * anything cached in local storage. Only once the role is known does it decide
 * where the visitor may go.
 */
export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) {
      router.replace('/login');
    }
  }, [user, loading, router]);

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-950 text-slate-400 text-sm">
        <Loader2 className="h-4 w-4 animate-spin mr-2" />
        Verifying credentials...
      </div>
    );
  }

  if (!user) return null;
  return <>{children}</>;
}

/**
 * Gate for admin-only pages.
 *
 * A non-admin is shown an explicit access-denied screen rather than a redirect,
 * so it is obvious the route exists but is not permitted.
 */
export function RequireAdmin({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) {
      router.replace('/login');
    } else if (!loading && user && user.role !== 'admin') {
      router.replace('/dashboard');
    }
  }, [user, loading, router]);

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-950 text-slate-400 text-sm">
        <Loader2 className="h-4 w-4 animate-spin mr-2" />
        Verifying permissions...
      </div>
    );
  }

  if (!user) return null;

  if (user.role !== 'admin') {
    return <AccessDenied />;
  }

  return <>{children}</>;
}

export function AccessDenied() {
  const router = useRouter();

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-950 px-4">
      <div className="w-full max-w-md rounded-2xl border border-red-500/20 bg-red-500/5 p-8 text-center">
        <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-red-500/10 text-red-400 border border-red-500/30">
          <Lock className="h-7 w-7" />
        </div>
        <h1 className="text-lg font-bold text-white">Access Denied</h1>
        <p className="mt-2 text-sm text-slate-400">
          Your account does not have permission to view this page.
        </p>
        <button
          onClick={() => router.replace('/dashboard')}
          className="mt-6 rounded-xl bg-slate-800 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 cursor-pointer"
        >
          Back to Dashboard
        </button>
      </div>
    </div>
  );
}

/** Honest empty state used everywhere data is genuinely absent. */
export function EmptyState({
  icon: Icon = ShieldAlert,
  title,
  hint,
}: {
  icon?: typeof ShieldAlert;
  title: string;
  hint?: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-slate-800 bg-slate-900/30 p-8 text-center">
      <Icon className="h-5 w-5 text-slate-600" />
      <div className="text-xs font-semibold text-slate-400">{title}</div>
      {hint && <div className="text-[11px] text-slate-600">{hint}</div>}
    </div>
  );
}

/** Used when a request fails. Never substitutes sample data. */
export function ErrorState({ message = 'Failed to load data.' }: { message?: string }) {
  return (
    <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-4 text-xs text-red-400">
      {message}
    </div>
  );
}
