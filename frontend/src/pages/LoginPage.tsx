import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useNavigate, useLocation } from 'react-router-dom';
import { z } from 'zod';

import { Logo } from '@/components/Logo';
import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { login, verifyMFALogin } from '@/features/auth/api';
import { extractError } from '@/lib/api';
import { useAuth } from '@/store/auth';

const schema = z.object({
  email: z.string().email('Enter a valid email'),
  password: z.string().min(8, 'At least 8 characters'),
});

type FormValues = z.infer<typeof schema>;

export function LoginPage() {
  const nav = useNavigate();
  const loc = useLocation();
  const setSession = useAuth((s) => s.setSession);
  const [submitError, setSubmitError] = useState<string | null>(null);
  /** Set once the password step passes on an MFA-protected account. */
  const [mfaToken, setMfaToken] = useState<string | null>(null);
  const [mfaCode, setMfaCode] = useState('');
  const [verifying, setVerifying] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { email: '', password: '' },
  });

  const finish = (user: Parameters<typeof setSession>[0]['user'], tokens: { access_token: string; refresh_token: string }) => {
    setSession({
      user,
      accessToken: tokens.access_token,
      refreshToken: tokens.refresh_token,
    });
    const redirectTo = (loc.state as { from?: string } | null)?.from ?? '/dashboard';
    nav(redirectTo, { replace: true });
  };

  const onSubmit = async (values: FormValues) => {
    setSubmitError(null);
    try {
      const result = await login(values.email, values.password);
      if (result.kind === 'mfa_required') {
        setMfaToken(result.mfaToken);
        return;
      }
      finish(result.user, result.tokens);
    } catch (e) {
      setSubmitError(extractError(e).message);
    }
  };

  const onVerifyMfa = async () => {
    setSubmitError(null);
    setVerifying(true);
    try {
      const { user, tokens } = await verifyMFALogin(mfaToken!, mfaCode);
      finish(user, tokens);
    } catch (e) {
      setSubmitError(extractError(e).message);
      setMfaCode('');
    } finally {
      setVerifying(false);
    }
  };

  return (
    <div className="min-h-full grid lg:grid-cols-2">
      <div className="hidden lg:flex bg-brand-600 text-white p-12 flex-col justify-between dark:bg-brand-700">
        <Logo />
        <div>
          <h1 className="text-4xl font-semibold leading-tight">
            Internal Ticketing<br />
            <span className="text-accent-200">for SUCCESS Bank.</span>
          </h1>
          <p className="mt-4 text-white/80 max-w-md">
            Branches raise issues. Admins triage. Agents resolve. Supervisors watch SLAs.
            Auditors review immutable logs. One platform.
          </p>
        </div>
        <span className="text-white/60 text-xs">© SUCCESS Bank — internal use only.</span>
      </div>

      <div className="flex items-center justify-center p-8 bg-[var(--bg)]">
        <Card className="w-full max-w-md">
          <h2 className="text-xl font-semibold text-[var(--tx)]">Sign in</h2>
          <p className="text-sm text-[var(--tx-2)] mt-1">Use your corporate credentials.</p>

          {submitError && (
            <div className="mt-4">
              <Badge tone="danger">{submitError}</Badge>
            </div>
          )}

          {/* Second factor — replaces the credential form once the password
              step passes, so there is no way to skip back past it. */}
          {mfaToken ? (
            <div className="mt-6 flex flex-col gap-4">
              <div>
                <span className="block mb-1 text-sm font-medium text-[var(--tx-2)]">
                  Authentication code
                </span>
                <p className="text-xs text-[var(--tx-3)] mb-2">
                  Enter the six-digit code from your authenticator app.
                </p>
                <input
                  className="input text-lg font-mono tracking-[0.4em] text-center"
                  value={mfaCode}
                  onChange={(e) => setMfaCode(e.target.value.replace(/[^\d]/g, '').slice(0, 6))}
                  onKeyDown={(e) => { if (e.key === 'Enter' && mfaCode.length === 6) onVerifyMfa(); }}
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  placeholder="000000"
                  autoFocus
                />
              </div>

              <Button onClick={onVerifyMfa} disabled={mfaCode.length !== 6 || verifying}>
                {verifying ? 'Verifying…' : 'Verify'}
              </Button>

              <button
                type="button"
                className="text-xs text-[var(--tx-3)] hover:text-[var(--tx-2)] underline"
                onClick={() => { setMfaToken(null); setMfaCode(''); setSubmitError(null); }}
              >
                Back to sign in
              </button>
            </div>
          ) : (
          <form className="mt-6 flex flex-col gap-4" onSubmit={handleSubmit(onSubmit)} noValidate>
            <label className="text-sm">
              <span className="block mb-1 font-medium text-[var(--tx-2)]">Work email</span>
              <input
                className="input"
                type="email"
                autoComplete="email"
                placeholder="you@successbank.com"
                {...register('email')}
              />
              {errors.email && <span className="text-xs text-[var(--err)]">{errors.email.message}</span>}
            </label>

            <label className="text-sm">
              <span className="block mb-1 font-medium text-[var(--tx-2)]">Password</span>
              <input
                className="input"
                type="password"
                autoComplete="current-password"
                placeholder="••••••••"
                {...register('password')}
              />
              {errors.password && (
                <span className="text-xs text-[var(--err)]">{errors.password.message}</span>
              )}
            </label>

            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? 'Signing in…' : 'Sign in'}
            </Button>

            <p className="text-xs text-[var(--tx-3)] text-center">
              Accounts with two-factor authentication will be asked for a code next.
            </p>
          </form>
          )}
        </Card>
      </div>
    </div>
  );
}
