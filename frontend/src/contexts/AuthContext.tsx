'use client';
import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  useMemo,
  ReactNode,
} from 'react';
import { User } from '@/lib/types';
import {
  fetchCurrentUser,
  login as apiLogin,
  logoutRequest,
  refreshToken as apiRefreshToken,
  registerAuthRefresh,
  registerSessionLostHandler,
  storeTokens,
  storeUser,
  clearTokens,
  clearUser,
  getRefreshToken,
  getAccessToken,
} from '@/lib/api';

interface AuthContextType {
  user: User | null;
  token: string | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  isAdmin: boolean;
  isInvigilator: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const clearSession = useCallback(() => {
    setToken(null);
    setUser(null);
    clearTokens();
    clearUser();
  }, []);

  const logout = useCallback(async () => {
    await logoutRequest();
    clearSession();
  }, [clearSession]);

  // 2-hour refresh token lifecycle handler
  const handleTokenRefresh = useCallback(async (): Promise<string | null> => {
    const currentRefresh = getRefreshToken();
    if (!currentRefresh) {
      clearSession();
      return null;
    }
    try {
      const data = await apiRefreshToken(currentRefresh);
      setToken(data.access_token);
      storeTokens(data.access_token, data.refresh_token);
      // Re-read the identity: an account deactivated mid-session must not keep
      // working just because its refresh token still parsed.
      const fresh = await fetchCurrentUser(data.access_token);
      setUser(fresh);
      storeUser(fresh);
      return data.access_token;
    } catch {
      clearSession();
      return null;
    }
  }, [clearSession]);

  useEffect(() => {
    registerAuthRefresh(handleTokenRefresh);
    registerSessionLostHandler(clearSession);
  }, [handleTokenRefresh, clearSession]);

  useEffect(() => {
    let cancelled = false;

    async function restore() {
      const storedToken = getAccessToken();
      if (!storedToken) {
        setLoading(false);
        return;
      }

      setToken(storedToken);
      // Ask the backend who this token belongs to. Until it answers, the role
      // is unknown and admin surfaces stay closed.
      try {
        const me = await fetchCurrentUser(storedToken);
        if (cancelled) return;
        setUser(me);
        storeUser(me);
      } catch {
        if (cancelled) return;
        // Expired access token: try one refresh before giving up.
        const refreshed = await handleTokenRefresh();
        if (!refreshed && !cancelled) {
          clearSession();
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    restore();
    return () => {
      cancelled = true;
    };
  }, [clearSession, handleTokenRefresh]);

  const login = useCallback(async (username: string, password: string) => {
    const data = await apiLogin(username, password);
    setToken(data.access_token);
    storeTokens(data.access_token, data.refresh_token);

    // The role comes from the server's token response, never from the form.
    const me = await fetchCurrentUser(data.access_token);
    setUser(me);
    storeUser(me);
  }, []);

  const value = useMemo(
    () => ({
      user,
      token,
      loading,
      login,
      logout,
      isAdmin: user?.role === 'admin',
      isInvigilator: user?.role === 'invigilator',
    }),
    [user, token, loading, login, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be within an AuthProvider');
  }
  return context;
}
