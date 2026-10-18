import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import * as authApi from '../api/auth';
import { migrateLocalSettings } from '../api/settings';
import AuthDialog from '../components/auth/AuthDialog';
import type { User } from '../types';

export interface Auth {
  user: User | null;
  /** 첫 로그인 상태 확인이 끝났는지 (끝나기 전에는 게스트처럼 보이지 않게 한다) */
  ready: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string, displayName: string) => Promise<void>;
  logout: () => Promise<void>;
  deleteAccount: (password: string) => Promise<void>;
  /** 로그인·가입 다이얼로그를 연다 */
  requestLogin: () => void;
}

const AuthContext = createContext<Auth | null>(null);

/** 로그인 상태를 앱 전체에 제공하고, 로그인·가입 다이얼로그를 한 곳에서 관리한다. */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    authApi
      .fetchMe()
      .then((u) => {
        if (!cancelled) setUser(u);
      })
      .catch(() => {
        // 서버에 닿지 않으면 게스트로 시작한다
      })
      .finally(() => {
        if (!cancelled) setReady(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // 로그인 직후 이 브라우저에 있던 설정을 계정으로 옮긴다 (계정에 이미 설정이 있으면 건드리지 않는다)
  const afterSignIn = useCallback(async (u: User) => {
    try {
      await migrateLocalSettings();
    } catch {
      // 설정 이전에 실패해도 로그인은 유효하다
    }
    setUser(u);
  }, []);

  const value = useMemo<Auth>(
    () => ({
      user,
      ready,
      login: async (email, password) => afterSignIn(await authApi.login(email, password)),
      signup: async (email, password, displayName) => afterSignIn(await authApi.signup(email, password, displayName)),
      logout: async () => {
        await authApi.logout();
        setUser(null);
      },
      deleteAccount: async (password) => {
        await authApi.deleteAccount(password);
        setUser(null);
      },
      requestLogin: () => setDialogOpen(true),
    }),
    [user, ready, afterSignIn],
  );

  return (
    <AuthContext.Provider value={value}>
      {children}
      <AuthDialog open={dialogOpen} onClose={() => setDialogOpen(false)} login={value.login} signup={value.signup} />
    </AuthContext.Provider>
  );
}

export function useAuth(): Auth {
  const auth = useContext(AuthContext);
  if (!auth) throw new Error('useAuth는 AuthProvider 안에서만 쓸 수 있어요.');
  return auth;
}
