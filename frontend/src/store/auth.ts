import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type Role =
  | 'branch_user' | 'admin' | 'agent' | 'supervisor' | 'auditor';

export interface OrgUnit {
  id: string;
  name: string;
  code: string;
  level: string | null;
}

export interface OrgRole {
  id: string;
  name: string;
  can_manage_unit: boolean;
  can_manage_subtree: boolean;
}

export interface AuthUser {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  branch_id: string | null;
  mfa_enabled: boolean;
  org_unit_id: string | null;
  org_unit: OrgUnit | null;
  org_role_id: string | null;
  org_role: OrgRole | null;
  is_super_admin: boolean;
}

interface AuthState {
  user: AuthUser | null;
  accessToken: string | null;
  refreshToken: string | null;
  setSession: (s: { user: AuthUser; accessToken: string; refreshToken: string }) => void;
  setTokens: (t: { accessToken: string; refreshToken: string }) => void;
  clear: () => void;
  hasRole: (...roles: Role[]) => boolean;
}

export const useAuth = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      accessToken: null,
      refreshToken: null,
      setSession: ({ user, accessToken, refreshToken }) => {
        localStorage.setItem('access_token', accessToken);
        set({ user, accessToken, refreshToken });
      },
      setTokens: ({ accessToken, refreshToken }) => {
        localStorage.setItem('access_token', accessToken);
        set({ accessToken, refreshToken });
      },
      clear: () => {
        localStorage.removeItem('access_token');
        set({ user: null, accessToken: null, refreshToken: null });
      },
      hasRole: (...roles) => {
        const r = get().user?.role;
        return r != null && roles.includes(r);
      },
    }),
    { name: 'success-auth' },
  ),
);
