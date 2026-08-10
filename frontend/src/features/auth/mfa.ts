import { api } from '@/lib/api';

export interface MFASetup {
  secret: string;
  otpauth_uri: string;
  /** Inline SVG markup, or null if the server could not render a QR code. */
  qr_svg: string | null;
  issuer: string;
  account: string;
}

/** Begin enrolment. Stores a secret but leaves MFA off until a code confirms it. */
export async function startMFASetup(): Promise<MFASetup> {
  const { data } = await api.post('/auth/mfa/setup');
  return data.data;
}

/** Confirm a code from the authenticator app and switch MFA on. */
export async function enableMFA(code: string): Promise<void> {
  await api.post('/auth/mfa/enable', { code });
}

/** Turn MFA off. Requires the account password, not just a live session. */
export async function disableMFA(password: string): Promise<void> {
  await api.post('/auth/mfa/disable', { password });
}

/** Clear another user's enrolment — admin recovery for a lost device. */
export async function resetUserMFA(userId: string): Promise<void> {
  await api.post(`/users/${userId}/mfa/reset`);
}
