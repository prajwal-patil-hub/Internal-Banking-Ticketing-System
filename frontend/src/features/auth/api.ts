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

export type LoginResult =
  | { kind: 'session'; user: AuthUser; tokens: TokenPair }
  /** Password accepted; the account also needs a six-digit code. */
  | { kind: 'mfa_required'; mfaToken: string };

export async function login(email: string, password: string): Promise<LoginResult> {
  try {
    const { data } = await api.post<LoginEnvelope>('/auth/login', { email, password });
    return { kind: 'session', ...data.data };
  } catch (err) {
    // MFA_REQUIRED is a 403 carrying a challenge token, not a failure — the
    // credentials were right and the caller should ask for the code.
    const error = (err as { response?: { data?: { error?: { code?: string; details?: { mfa_token?: string } } } } })
      .response?.data?.error;
    if (error?.code === 'MFA_REQUIRED' && error.details?.mfa_token) {
      return { kind: 'mfa_required', mfaToken: error.details.mfa_token };
    }
    throw err;
  }
}

/** Finish an MFA login by exchanging the challenge token plus a code. */
export async function verifyMFALogin(
  mfaToken: string,
  code: string,
): Promise<{ user: AuthUser; tokens: TokenPair }> {
  const { data } = await api.post<LoginEnvelope>('/auth/mfa/verify', {
    mfa_token: mfaToken,
    code,
  });
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
