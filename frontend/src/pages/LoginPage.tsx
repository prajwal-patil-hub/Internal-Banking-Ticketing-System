import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useNavigate, useLocation } from 'react-router-dom';
import { z } from 'zod';
import { motion } from 'framer-motion';
import { Mail, Lock, ArrowRight, ShieldCheck, Eye, EyeOff } from 'lucide-react';

import { Logo } from '@/components/Logo';
import { Badge } from '@/components/Badge';
import { login } from '@/features/auth/api';
import { extractError } from '@/lib/api';
import { useAuth } from '@/store/auth';

const schema = z.object({
  email: z.string().min(3, 'Enter a valid email'),
  password: z.string().min(8, 'At least 8 characters'),
});

type FormValues = z.infer<typeof schema>;

export function LoginPage() {
  const nav = useNavigate();
  const loc = useLocation();
  const setSession = useAuth((s) => s.setSession);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [showPassword, setShowPassword] = useState(false);

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
    <div className="min-h-screen flex items-center justify-center px-4 py-10 sm:py-16">
      <div className="grid w-full max-w-5xl lg:grid-cols-2 gap-8 lg:gap-12">
        {/* Brand panel */}
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
          className="hidden lg:flex flex-col justify-between glass rounded-4xl p-10 relative overflow-hidden"
        >
          <div className="absolute -top-20 -right-20 h-72 w-72 rounded-full"
               style={{ background: 'radial-gradient(circle, rgba(99,102,241,0.25), transparent 60%)' }} />
          <div className="absolute -bottom-32 -left-10 h-72 w-72 rounded-full"
               style={{ background: 'radial-gradient(circle, rgba(167,139,250,0.18), transparent 60%)' }} />

          <Logo size="md" />

          <div className="relative z-10">
            <h1 className="text-5xl font-semibold tracking-tight text-ink leading-[1.05]">
              Internal Ticketing
              <br />
              <span className="bg-clip-text text-transparent" style={{
                backgroundImage: 'linear-gradient(135deg, #4F46E5 0%, #8B5CF6 60%, #EC4899 100%)',
              }}>
                for SUCCESS Bank.
              </span>
            </h1>
            <p className="mt-5 text-md text-ink-muted max-w-md leading-relaxed">
              Branches raise issues. Admins triage. Agents resolve. Supervisors watch SLAs.
              Auditors review immutable logs. One platform.
            </p>

            <div className="mt-8 grid grid-cols-2 gap-3 max-w-md">
              <Stat label="Branches"   value="5" />
              <Stat label="Active SLAs" value="4" />
              <Stat label="Roles"       value="5" />
              <Stat label="Audit"       value="Immutable" />
            </div>
          </div>

          <div className="relative z-10 flex items-center gap-2 text-xs text-ink-muted">
            <ShieldCheck className="h-3.5 w-3.5 text-success-deep" />
            Internal use only · TLS · MFA · Audit-grade
          </div>
        </motion.div>

        {/* Auth card */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.42, ease: [0.22, 1, 0.36, 1], delay: 0.05 }}
          className="glass-strong rounded-4xl p-7 sm:p-9 self-center"
        >
          <div className="lg:hidden mb-5">
            <Logo size="md" />
          </div>

          <h2 className="text-3xl font-semibold tracking-tight text-ink">Welcome back</h2>
          <p className="mt-1.5 text-sm text-ink-muted">Sign in with your corporate credentials.</p>

          {submitError && (
            <div className="mt-5">
              <Badge tone="danger">{submitError}</Badge>
            </div>
          )}

          <form className="mt-6 flex flex-col gap-4" onSubmit={handleSubmit(onSubmit)} noValidate>
            <label className="flex flex-col gap-1.5">
              <span className="label">Work email</span>
              <div className="relative">
                <Mail className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-ink-subtle pointer-events-none" />
                <input
                  className="input pl-10"
                  type="email"
                  autoComplete="email"
                  placeholder="you@successbank.com"
                  {...register('email')}
                />
              </div>
              {errors.email && <span className="text-2xs text-danger-deep">{errors.email.message}</span>}
            </label>

            <label className="flex flex-col gap-1.5">
              <span className="label">Password</span>
              <div className="relative">
                <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-ink-subtle pointer-events-none" />
                <input
                  className="input pl-10 pr-11"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                  placeholder="••••••••"
                  {...register('password')}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  aria-pressed={showPassword}
                  className="absolute right-2 top-1/2 -translate-y-1/2 h-8 w-8 grid place-items-center rounded-pill text-ink-muted hover:text-ink hover:bg-white/70 transition-colors"
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
              {errors.password && (
                <span className="text-2xs text-danger-deep">{errors.password.message}</span>
              )}
            </label>

            <button type="submit" disabled={isSubmitting} className="btn-primary mt-2 group">
              {isSubmitting ? 'Signing in…' : (
                <>
                  Sign in
                  <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
                </>
              )}
            </button>

            <p className="text-2xs text-ink-muted text-center mt-2">
              Privileged roles will be prompted for MFA on first sign-in.
            </p>
          </form>
        </motion.div>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="glass-subtle rounded-2xl p-3.5">
      <div className="text-2xs uppercase tracking-wider text-ink-muted">{label}</div>
      <div className="text-xl font-semibold tracking-tight text-ink mt-0.5">{value}</div>
    </div>
  );
}
