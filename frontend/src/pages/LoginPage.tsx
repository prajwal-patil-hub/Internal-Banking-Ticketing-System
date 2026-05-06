import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useNavigate, useLocation } from 'react-router-dom';
import { z } from 'zod';

import { Logo } from '@/components/Logo';
import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { login } from '@/features/auth/api';
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

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    defaultValues: { email: '', password: '' },
  });

  const onSubmit = async (values: FormValues) => {
    setSubmitError(null);
    const parsed = schema.safeParse(values);
    if (!parsed.success) {
      setSubmitError(parsed.error.issues[0]?.message ?? 'Invalid input.');
      return;
    }
    try {
      const { user, tokens } = await login(parsed.data.email, parsed.data.password);
      setSession({
        user,
        accessToken: tokens.access_token,
        refreshToken: tokens.refresh_token,
      });
      const redirectTo = (loc.state as { from?: string } | null)?.from ?? '/dashboard';
      nav(redirectTo, { replace: true });
    } catch (e) {
      setSubmitError(extractError(e).message);
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

      <div className="flex items-center justify-center p-8 bg-surface-muted dark:bg-slate-950">
        <Card className="w-full max-w-md">
          <h2 className="text-xl font-semibold">Sign in</h2>
          <p className="text-sm text-slate-500 mt-1">Use your corporate credentials.</p>

          {submitError && (
            <div className="mt-4">
              <Badge tone="danger">{submitError}</Badge>
            </div>
          )}

          <form className="mt-6 flex flex-col gap-4" onSubmit={handleSubmit(onSubmit)} noValidate>
            <label className="text-sm">
              <span className="block mb-1 font-medium">Work email</span>
              <input
                className="input"
                type="email"
                autoComplete="email"
                placeholder="you@successbank.com"
                {...register('email')}
              />
              {errors.email && <span className="text-xs text-red-600">{errors.email.message}</span>}
            </label>

            <label className="text-sm">
              <span className="block mb-1 font-medium">Password</span>
              <input
                className="input"
                type="password"
                autoComplete="current-password"
                placeholder="••••••••"
                {...register('password')}
              />
              {errors.password && (
                <span className="text-xs text-red-600">{errors.password.message}</span>
              )}
            </label>

            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? 'Signing in…' : 'Sign in'}
            </Button>

            <p className="text-xs text-slate-500 text-center">
              MFA prompt appears after first login (P8).
            </p>
          </form>
        </Card>
      </div>
    </div>
  );
}
