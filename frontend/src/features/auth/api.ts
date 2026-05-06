import { api } from '@/lib/api';
import type { AuthUser } from '@/store/auth';

interface TokenPair {
  access_token: string;
  access_expires_at: string;
  refresh_token: string;
  refresh_expires_at: string;
  token_type: string;
}

interface LoginEnvelope {
  success: boolean;
  data: { user: AuthUser; tokens: TokenPair };
  error: null | { code: string; message: string };
}

interface RefreshEnvelope {
  success: boolean;
  data: TokenPair;
  error: null | { code: string; message: string };
}

interface MeEnvelope {
  success: boolean;
  data: AuthUser;
}

export async function login(email: string, password: string): Promise<{ user: AuthUser; tokens: TokenPair }> {
  const { data } = await api.post<LoginEnvelope>('/auth/login', { email, password });
  return data.data;
}

export async function refreshTokens(refresh_token: string): Promise<TokenPair> {
  const { data } = await api.post<RefreshEnvelope>('/auth/refresh', { refresh_token });
  return data.data;
}

export async function logout(refresh_token: string | null): Promise<void> {
  await api.post('/auth/logout', { refresh_token });
}

export async function fetchMe(): Promise<AuthUser> {
  const { data } = await api.get<MeEnvelope>('/users/me');
  return data.data;
}
