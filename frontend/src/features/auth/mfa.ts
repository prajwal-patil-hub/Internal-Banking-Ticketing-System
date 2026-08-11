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

export interface MFAEnableResult {
  mfa_enabled: boolean;
  /** Shown exactly once — only hashes are stored, so they cannot be re-fetched. */
  backup_codes: string[];
  backup_codes_notice: string;
}

/** Confirm a code from the authenticator app and switch MFA on. */
export async function enableMFA(code: string): Promise<MFAEnableResult> {
  const { data } = await api.post('/auth/mfa/enable', { code });
  return data.data;
}

export interface BackupCodeStatus {
  total: number;
  remaining: number;
  used: number;
  can_regenerate: boolean;
}

export async function getBackupCodeStatus(): Promise<BackupCodeStatus> {
  const { data } = await api.get('/auth/mfa/backup-codes');
  return data.data;
}

/** Replace every code. Requires the password — see the route's docstring. */
export async function regenerateBackupCodes(password: string): Promise<string[]> {
  const { data } = await api.post('/auth/mfa/backup-codes/regenerate', { password });
  return data.data.backup_codes;
}

/** Turn MFA off. Requires the account password, not just a live session. */
export async function disableMFA(password: string): Promise<void> {
  await api.post('/auth/mfa/disable', { password });
}

/** Clear another user's enrolment — admin recovery for a lost device. */
export async function resetUserMFA(userId: string): Promise<void> {
  await api.post(`/users/${userId}/mfa/reset`);
}
