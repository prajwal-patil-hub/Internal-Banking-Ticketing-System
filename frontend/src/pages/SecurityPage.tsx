import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Button } from '@/components/Button';
import { CodeInput } from '@/components/CodeInput';
import { BackupCodes } from '@/components/BackupCodes';
import { cn } from '@/lib/cn';
import { extractError } from '@/lib/api';
import { useAuth } from '@/store/auth';
import {
  startMFASetup,
  enableMFA,
  disableMFA,
  getBackupCodeStatus,
  regenerateBackupCodes,
  type MFASetup,
} from '@/features/auth/mfa';

type Stage = 'idle' | 'enrolling' | 'showing-codes' | 'disabling';


/**
 * Three-step progress rail.
 *
 * The enrolment is genuinely sequential and can fail at the last step, so
 * showing where you are — and that a confirmed code is still owed — stops the
 * QR screen reading like the end of the process.
 */
function StepRail({ current }: { current: 1 | 2 | 3 }) {
  const steps = ['Verify password', 'Scan QR code', 'Confirm code'] as const;
  return (
    <ol className="flex items-center justify-center gap-2 sm:gap-4" aria-label="Enrolment progress">
      {steps.map((label, i) => {
        const step = (i + 1) as 1 | 2 | 3;
        const done = step < current;
        const active = step === current;
        return (
          <li key={label} className="flex items-center gap-2 sm:gap-4">
            <div className="flex flex-col items-center gap-1.5">
              <span
                aria-current={active ? 'step' : undefined}
                className={cn(
                  'h-8 w-8 rounded-full flex items-center justify-center text-xs font-bold',
                  'transition-colors',
                  done && 'bg-[var(--brand)] text-white',
                  active && 'bg-[var(--brand-xs)] text-[var(--brand)] ring-2 ring-[var(--brand)]',
                  !done && !active && 'bg-[var(--inset)] text-[var(--tx-3)]',
                )}
              >
                {done ? (
                  <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                       strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M20 6 9 17l-5-5" />
                  </svg>
                ) : step}
              </span>
              <span className={cn(
                'text-[10px] whitespace-nowrap',
                active ? 'text-[var(--tx)] font-medium' : 'text-[var(--tx-3)]',
              )}>
                {label}
              </span>
            </div>
            {i < steps.length - 1 && (
              <span className={cn(
                'h-px w-8 sm:w-16 -mt-5',
                done ? 'bg-[var(--brand)]' : 'bg-[var(--line)]',
              )} />
            )}
          </li>
        );
      })}
    </ol>
  );
}

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
  /** Held only until the user confirms they have saved them. */
  const [freshCodes, setFreshCodes] = useState<string[]>([]);

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
    onSuccess: (result) => {
      syncUser(true);
      // Straight to the codes rather than back to idle: this is the only
      // moment they exist in plaintext.
      setFreshCodes(result.backup_codes);
      setStage('showing-codes');
      setCode('');
      setError(null);
    },
    onError: (e) => setError(extractError(e).message),
  });

  const { data: codeStatus } = useQuery({
    queryKey: ['mfa-backup-codes', mfaEnabled],
    queryFn: getBackupCodeStatus,
    enabled: mfaEnabled,
  });

  const regenerate = useMutation({
    mutationFn: () => regenerateBackupCodes(password),
    onSuccess: (codes) => {
      setFreshCodes(codes);
      setStage('showing-codes');
      setPassword('');
      setError(null);
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
          <div className="mt-6 flex flex-col items-center gap-6">
            {/* Password was verified to reach this screen, so step 1 is done;
                the code decides whether step 3 completes. */}
            <StepRail current={code.length === 6 ? 3 : 2} />

            {setup.qr_svg ? (
              <div className="rounded-2xl bg-white p-4 border border-[var(--line)] shadow-sm">
                {/* Server-generated SVG from our own otpauth URI. */}
                <div dangerouslySetInnerHTML={{ __html: setup.qr_svg }} />
              </div>
            ) : (
              <p className="text-sm text-[var(--warn)] text-center max-w-sm">
                QR code unavailable on this server build — use the setup key below.
              </p>
            )}

            <p className="text-sm text-[var(--tx-2)] text-center max-w-sm">
              Open <strong>Google Authenticator</strong>, <strong>Authy</strong> or any
              TOTP app and scan the code above.
            </p>

            <div className="w-full max-w-sm">
              <p className="text-[11px] uppercase tracking-widest text-[var(--tx-3)] font-semibold mb-2">
                Or enter the setup key manually
              </p>
              <div className="flex items-center gap-2">
                <code className="flex-1 text-sm font-mono px-3 py-2.5 rounded-lg bg-[var(--inset)] border border-[var(--line)] tracking-[0.15em] text-[var(--tx)] break-all">
                  {secretShown
                    ? setup.secret.replace(/(.{4})/g, '$1 ').trim()
                    : '•'.repeat(setup.secret.length)}
                </code>
                <Button variant="ghost" onClick={() => setSecretShown((v) => !v)}
                        title={secretShown ? 'Hide the key' : 'Show the key'}>
                  {secretShown ? 'Hide' : 'Show'}
                </Button>
                <Button variant="ghost"
                        onClick={() => navigator.clipboard?.writeText(setup.secret)}
                        title="Copy the key">
                  Copy
                </Button>
              </div>
            </div>

            <div className="w-full max-w-sm flex flex-col items-center gap-3">
              <p className="text-[11px] uppercase tracking-widest text-[var(--tx-3)] font-semibold">
                Enter the 6-digit code from your app
              </p>
              <CodeInput
                value={code}
                onChange={setCode}
                disabled={enableMutation.isPending}
                autoFocus
                onComplete={() => enableMutation.mutate()}
              />
            </div>

            <div className="flex gap-2 w-full max-w-sm">
              <Button
                onClick={() => enableMutation.mutate()}
                disabled={code.length !== 6 || enableMutation.isPending}
                className="flex-1"
              >
                {enableMutation.isPending ? 'Verifying…' : 'Verify & Enable MFA'}
              </Button>
              <Button variant="ghost" onClick={reset}>Cancel</Button>
            </div>

            <p className="text-xs text-[var(--tx-3)] text-center max-w-sm border-t border-[var(--line)] pt-4">
              Keep the setup key somewhere safe. There are no printed backup codes yet —
              if you lose the device, an administrator has to clear the enrolment for you.
            </p>
          </div>
        )}

        {/* ── Recovery codes, shown once ───────────────────────────────── */}
        {stage === 'showing-codes' && (
          <div className="mt-6 flex flex-col items-center gap-4">
            <BackupCodes
              codes={freshCodes}
              onDone={() => {
                setFreshCodes([]);
                reset();
                setNotice('Two-factor authentication is on. You will be asked for a code at each sign-in.');
              }}
            />
          </div>
        )}

        {/* ── Recovery code status, once enrolled ──────────────────────── */}
        {stage === 'idle' && mfaEnabled && codeStatus && (
          <div className="mt-4 pt-4 border-t border-[var(--line)] flex items-center justify-between gap-3 flex-wrap">
            <div>
              <p className="text-sm text-[var(--tx)]">
                Recovery codes:{' '}
                <span className={cn(
                  'font-semibold',
                  codeStatus.remaining <= 2 ? 'text-[var(--warn)]' : 'text-[var(--tx)]',
                )}>
                  {codeStatus.remaining} of {codeStatus.total} left
                </span>
              </p>
              <p className="text-xs text-[var(--tx-3)] mt-0.5">
                {codeStatus.remaining <= 2
                  ? 'Running low — generate a new set while you still can.'
                  : 'Each signs you in once if you lose your phone.'}
              </p>
            </div>
            <Button variant="ghost" onClick={() => setStage('regenerating' as Stage)}>
              Generate new codes
            </Button>
          </div>
        )}

        {/* ── Regenerating ─────────────────────────────────────────────── */}
        {(stage as string) === 'regenerating' && (
          <div className="mt-5 space-y-3">
            <label htmlFor="regen-pw" className="text-sm text-[var(--tx-2)] block">
              Confirm your password. This invalidates every existing code.
            </label>
            <div className="flex items-center gap-2 flex-wrap">
              <input
                id="regen-pw"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                placeholder="Your password"
                className="w-64 rounded-lg border border-[var(--line)] bg-[var(--bg)] px-3 py-2 text-sm text-[var(--tx)] outline-none focus:border-[var(--brand)]"
              />
              <Button
                onClick={() => regenerate.mutate()}
                disabled={!password || regenerate.isPending}
              >
                {regenerate.isPending ? 'Generating…' : 'Generate'}
              </Button>
              <Button variant="ghost" onClick={reset}>Cancel</Button>
            </div>
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
