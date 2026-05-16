import { createContext, useContext, useState } from 'react';
import type { ReactNode } from 'react';
import type { UserRole } from '../types';

export interface AuthState {
  token: string | null;
  role: UserRole | null;
  login: (token: string, role: UserRole) => void;
  logout: () => void;
  hasRole: (minRole: UserRole) => boolean;
}

export const ROLE_LEVEL: Record<UserRole, number> = {
  admin: 4,
  reviewer: 3,
  importer: 2,
  viewer: 1,
};

export const AuthContext = createContext<AuthState>({} as AuthState);

export function useAuthState(): AuthState {
  const [token, setToken] = useState<string | null>(localStorage.getItem('access_token'));
  const [role, setRole] = useState<UserRole | null>(
    localStorage.getItem('user_role') as UserRole | null
  );

  const login = (t: string, r: UserRole) => {
    localStorage.setItem('access_token', t);
    localStorage.setItem('user_role', r);
    setToken(t);
    setRole(r);
  };

  const logout = () => {
    localStorage.clear();
    setToken(null);
    setRole(null);
  };

  const hasRole = (minRole: UserRole) =>
    role ? ROLE_LEVEL[role] >= ROLE_LEVEL[minRole] : false;

  return { token, role, login, logout, hasRole };
}

// AuthProvider component is defined in App.tsx to allow JSX usage
export const useAuth = () => useContext(AuthContext);

// Re-export ReactNode type for use in AuthProvider
export type { ReactNode };
