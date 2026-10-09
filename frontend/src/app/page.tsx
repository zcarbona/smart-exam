'use client';
import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';

export default function Home() {
  const router = useRouter();
  const { user, loading } = useAuth();

  useEffect(() => {
    // Wait until the server has confirmed the identity. Routing before that
    // would decide based on a cached, attacker-controllable value.
    if (loading) return;

    if (!user) {
      router.replace('/login');
    } else {
      router.replace('/dashboard');
    }
  }, [user, loading, router]);

  return (
    <div className="flex h-screen items-center justify-center bg-slate-950">
      <div className="text-slate-400 text-sm">Loading Smart Exam System...</div>
    </div>
  );
}
