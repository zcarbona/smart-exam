'use client';
import { createContext, useContext, useState, useEffect, ReactNode, useCallback } from 'react';
import { User } from '@/lib/types';
import {
  login as apiLogin,
  getCurrentUser,
  refreshToken as apiRefreshToken,
  registerAuthRefresh,
} from '@/lib/api';

interface AuthContextType {
  user: User | null;
  token: string | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [refreshTokenStr, setRefreshTokenStr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const logout = useCallback(() => {
    setToken(null);
    setRefreshTokenStr(null);
    setUser(null);
    if (typeof window !== 'undefined') {
      localStorage.removeItem('smartexam_token');
      localStorage.removeItem('smartexam_refresh_token');
      localStorage.removeItem('smartexam_user');
    }
  }, []);

  // 2-hour refresh token lifecycle handler (adapted from ProjectAlpha)
  const handleTokenRefresh = useCallback(async (): Promise<string | null> => {
    const currentRefresh = typeof window !== 'undefined' ? localStorage.getItem('smartexam_refresh_token') : null;
    if (!currentRefresh) {
      logout();
      return null;
    }
    try {
      const data = await apiRefreshToken(currentRefresh);
      setToken(data.access_token);
      setRefreshTokenStr(data.refresh_token);
      localStorage.setItem('smartexam_token', data.access_token);
      localStorage.setItem('smartexam_refresh_token', data.refresh_token);
      return data.access_token;
    } catch {
      logout();
      return null;
    }
  }, [logout]);

  useEffect(() => {
    registerAuthRefresh(handleTokenRefresh);
  }, [handleTokenRefresh]);

  useEffect(() => {
    const storedToken = localStorage.getItem('smartexam_token');
    const storedRefresh = localStorage.getItem('smartexam_refresh_token');
    const storedUser = localStorage.getItem('smartexam_user');

    if (storedToken && storedUser) {
      setToken(storedToken);
      setRefreshTokenStr(storedRefresh);
      try {
        setUser(JSON.parse(storedUser));
      } catch {
        logout();
      }
    }
    setLoading(false);
  }, [logout]);

  const login = async (username: string, password: string) => {
    const data = await apiLogin(username, password);
    const userData = await getCurrentUser(data.access_token);
    setToken(data.access_token);
    setRefreshTokenStr(data.refresh_token);
    setUser(userData);

    localStorage.setItem('smartexam_token', data.access_token);
    localStorage.setItem('smartexam_refresh_token', data.refresh_token);
    localStorage.setItem('smartexam_user', JSON.stringify(userData));
  };

  return (
    <AuthContext.Provider value={{ user, token, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
