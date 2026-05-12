import { api } from '@/lib/api';

interface Envelope<T> { data: T }

export async function mfaEnroll() {
  const { data } = await api.post<Envelope<{ secret: string; otpauth_uri: string }>>('/mfa/enroll');
  return data.data;
}

export async function mfaVerify(code: string) {
  const { data } = await api.post<Envelope<{ mfa_enabled: boolean }>>('/mfa/verify', { code });
  return data.data;
}

export async function mfaDisable(code: string) {
  const { data } = await api.post<Envelope<{ mfa_enabled: boolean }>>('/mfa/disable', { code });
  return data.data;
}
