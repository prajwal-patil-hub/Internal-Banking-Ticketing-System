import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Button } from '@/components/Button';
import { cn } from '@/lib/cn';
import { extractError } from '@/lib/api';
import { useAuth } from '@/store/auth';
import { startMFASetup, enableMFA, disableMFA, type MFASetup } from '@/features/auth/mfa';

type Stage = 'idle' | 'enrolling' | 'disabling';

export function SecurityPage() {
  const user = useAuth((s) => s.user);
  const setUser = useAuth((s) => s.setSession);
  const accessToken = useAuth((s) => s.accessToken);
  const refreshToken = useAuth((s) => s.refreshToken);

  const [stage, setStage] = useState<Stage>('idle');
  const [setup, setSetup] = useState<MFASetup | null>(null);
  const [code, setCode] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [secretShown, setSecretShown] = useState(false);

  const mfaEnabled = user?.mfa_enabled ?? false;

  /** Keep the cached session in step with the server after a change. */
  const syncUser = (enabled: boolean) => {
    if (user && accessToken && refreshToken) {
      setUser({ user: { ...user, mfa_enabled: enabled }, accessToken, refreshToken });
    }
  };

  const reset = () => {
    setStage('idle');
    setSetup(null);
    setCode('');
    setPassword('');
    setError(null);
    setSecretShown(false);
  };

  const setupMutation = useMutation({
    mutationFn: startMFASetup,
    onSuccess: (data) => {
      setSetup(data);
      setStage('enrolling');
      setError(null);
      setNotice(null);
    },
    onError: (e) => setError(extractError(e).message),
  });

  const enableMutation = useMutation({
    mutationFn: () => enableMFA(code),
    onSuccess: () => {
      syncUser(true);
      reset();
      setNotice('Two-factor authentication is on. You will be asked for a code at each sign-in.');
    },
    onError: (e) => setError(extractError(e).message),
  });

  const disableMutation = useMutation({
    mutationFn: () => disableMFA(password),
    onSuccess: () => {
      syncUser(false);
      reset();
      setNotice('Two-factor authentication is off.');
    },
    onError: (e) => setError(extractError(e).message),
  });

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-xl font-semibold text-[var(--tx)]">Security</h1>
        <p className="text-xs text-[var(--tx-3)] mt-0.5">
          Manage the protection on your own account.
        </p>
      </div>

      {notice && (
        <div className="card-sm p-3 text-sm text-[var(--ok)] flex items-start gap-2">
          <svg className="h-4 w-4 shrink-0 mt-0.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M20 6 9 17l-5-5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <span>{notice}</span>
        </div>
      )}

      <section className="card-sm p-5">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h2 className="text-base font-semibold text-[var(--tx)]">
              Two-factor authentication
            </h2>
            <p className="text-sm text-[var(--tx-3)] mt-1 max-w-md">
              Adds a six-digit code from an authenticator app to your sign-in, so a
              stolen password alone is not enough to reach the account.
            </p>
          </div>
          <span className={cn('pill', mfaEnabled ? 'pill-ok' : 'pill-warn')}>
            {mfaEnabled ? 'On' : 'Off'}
          </span>
        </div>

        {user?.is_super_admin && !mfaEnabled && (
          <p className="mt-3 text-sm text-[var(--warn)]">
            This account holds super admin privileges. Turning on two-factor
            authentication is strongly recommended.
          </p>
        )}

        {error && (
          <div className="mt-4 card-sm p-3 text-sm text-[var(--err)]">{error}</div>
        )}

        {/* ── Idle ─────────────────────────────────────────────────────── */}
        {stage === 'idle' && (
          <div className="mt-5 flex gap-2">
            {mfaEnabled ? (
              <Button variant="ghost" onClick={() => { setStage('disabling'); setNotice(null); }}>
                Turn off
              </Button>
            ) : (
              <Button
                onClick={() => setupMutation.mutate()}
                disabled={setupMutation.isPending}
              >
                {setupMutation.isPending ? 'Preparing…' : 'Set up two-factor'}
              </Button>
            )}
          </div>
        )}

        {/* ── Enrolling ────────────────────────────────────────────────── */}
        {stage === 'enrolling' && setup && (
          <div className="mt-5 space-y-5">
            <ol className="space-y-5">
              <li>
                <p className="text-sm font-medium text-[var(--tx)]">
                  1. Scan this with your authenticator app
                </p>
                <p className="text-xs text-[var(--tx-3)] mt-0.5">
                  Google Authenticator, 1Password, Authy — any TOTP app works.
                </p>
                {setup.qr_svg ? (
                  <div
                    className="mt-3 inline-block rounded-lg bg-white p-3 border border-[var(--line)]"
                    // Server-generated SVG from our own otpauth URI.
                    dangerouslySetInnerHTML={{ __html: setup.qr_svg }}
                  />
                ) : (
                  <p className="mt-3 text-sm text-[var(--warn)]">
                    QR code unavailable on this server build — use the setup key below.
                  </p>
                )}
              </li>

              <li>
                <p className="text-sm font-medium text-[var(--tx)]">
                  Can&apos;t scan? Enter the key by hand
                </p>
                <div className="mt-2 flex items-center gap-2 flex-wrap">
                  <code className="text-sm font-mono px-2 py-1 rounded bg-[var(--bg-2)] border border-[var(--line)] tracking-wider">
                    {secretShown ? setup.secret : '•'.repeat(setup.secret.length)}
                  </code>
                  <Button variant="ghost" onClick={() => setSecretShown((v) => !v)}>
                    {secretShown ? 'Hide' : 'Show'}
                  </Button>
                  <Button
                    variant="ghost"
                    onClick={() => navigator.clipboard?.writeText(setup.secret)}
                  >
                    Copy
                  </Button>
                </div>
              </li>

              <li>
                <label htmlFor="mfa-code" className="text-sm font-medium text-[var(--tx)]">
                  2. Enter the six-digit code it shows
                </label>
                <div className="mt-2 flex items-center gap-2 flex-wrap">
                  <input
                    id="mfa-code"
                    value={code}
                    onChange={(e) => setCode(e.target.value.replace(/[^\d]/g, '').slice(0, 6))}
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    placeholder="000000"
                    className="w-32 rounded-lg border border-[var(--line)] bg-[var(--bg)] px-3 py-2 text-lg font-mono tracking-[0.3em] text-[var(--tx)] outline-none focus:border-[var(--brand)]"
                  />
                  <Button
                    onClick={() => enableMutation.mutate()}
                    disabled={code.length !== 6 || enableMutation.isPending}
                  >
                    {enableMutation.isPending ? 'Verifying…' : 'Verify and turn on'}
                  </Button>
                  <Button variant="ghost" onClick={reset}>Cancel</Button>
                </div>
              </li>
            </ol>

            <p className="text-xs text-[var(--tx-3)] border-t border-[var(--line)] pt-3">
              Keep the setup key somewhere safe. There are no printed backup codes yet —
              if you lose the device, an administrator has to clear the enrolment for you.
            </p>
          </div>
        )}

        {/* ── Disabling ────────────────────────────────────────────────── */}
        {stage === 'disabling' && (
          <div className="mt-5 space-y-3">
            <label htmlFor="mfa-pw" className="text-sm text-[var(--tx-2)] block">
              Confirm your password to turn two-factor authentication off.
            </label>
            <div className="flex items-center gap-2 flex-wrap">
              <input
                id="mfa-pw"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                placeholder="Your password"
                className="w-64 rounded-lg border border-[var(--line)] bg-[var(--bg)] px-3 py-2 text-sm text-[var(--tx)] outline-none focus:border-[var(--brand)]"
              />
              <Button
                variant="danger"
                onClick={() => disableMutation.mutate()}
                disabled={!password || disableMutation.isPending}
              >
                {disableMutation.isPending ? 'Turning off…' : 'Turn off'}
              </Button>
              <Button variant="ghost" onClick={reset}>Cancel</Button>
            </div>
          </div>
        )}
      </section>

      <section className="card-sm p-5">
        <h2 className="text-base font-semibold text-[var(--tx)]">Account</h2>
        <dl className="mt-3 grid gap-x-6 gap-y-2 text-sm" style={{ gridTemplateColumns: 'auto 1fr' }}>
          <dt className="text-[var(--tx-3)]">Signed in as</dt>
          <dd className="text-[var(--tx)]">{user?.email}</dd>
          <dt className="text-[var(--tx-3)]">Role</dt>
          <dd className="text-[var(--tx)]">
            {user?.role}
            {user?.is_super_admin && <span className="pill pill-info ml-2">super admin</span>}
          </dd>
        </dl>
      </section>
    </div>
  );
}
