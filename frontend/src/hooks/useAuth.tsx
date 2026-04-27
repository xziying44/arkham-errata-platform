import { createContext, useContext, useState, useCallback, useEffect } from 'react';
import type { ReactNode } from 'react';
import type { User } from '../types';

interface AuthContextType {
  user: User | null;
  token: string | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  isAdmin: boolean;
  canErrata: boolean;
  canReview: boolean;
  canAdmin: boolean;
}

const AuthContext = createContext<AuthContextType>(null!);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(localStorage.getItem('token'));
  const [loading, setLoading] = useState(Boolean(token));

  useEffect(() => {
    if (!token) {
      setLoading(false);
      return;
    }
    const loadUser = async () => {
      try {
        const { fetchCurrentUser } = await import('../api/auth');
        const data = await fetchCurrentUser();
        setUser(data);
      } catch {
        localStorage.removeItem('token');
        setToken(null);
        setUser(null);
      } finally {
        setLoading(false);
      }
    };
    loadUser();
  }, [token]);

  const loginFn = useCallback(async (username: string, password: string) => {
    const { login } = await import('../api/auth');
    const data = await login(username, password);
    localStorage.setItem('token', data.token);
    setToken(data.token);
    setUser({ id: data.user_id, username: data.username, role: data.role, note: '', is_active: true });
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem('token');
    setToken(null);
    setUser(null);
  }, []);

  const canAdmin = user?.role === '管理员';
  const canErrata = user?.role === '勘误员' || canAdmin;
  const canReview = user?.role === '审核员' || canAdmin;

  return (
    <AuthContext.Provider value={{ user, token, loading, login: loginFn, logout, isAdmin: canAdmin, canErrata, canReview, canAdmin }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
