import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { useNavigate } from 'react-router-dom';
import { z } from 'zod';
import { motion } from 'framer-motion';
import { Eye, EyeOff, KeyRound, Mail, ShieldCheck, Shield, Building2 } from 'lucide-react';

import { api, extractError } from '@/lib/api';
import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { useToasts } from '@/components/Toast';
import { useAuth } from '@/store/auth';

const schema = z
  .object({
    current_password: z.string().min(8, 'At least 8 characters'),
    new_password: z.string().min(8, 'At least 8 characters'),
    confirm_password: z.string().min(8, 'At least 8 characters'),
  })
  .refine((d) => d.new_password === d.confirm_password, {
    path: ['confirm_password'],
    message: "New password and confirmation don't match.",
  })
  .refine((d) => d.new_password !== d.current_password, {
    path: ['new_password'],
    message: 'New password must differ from the current one.',
  });

type Form = z.infer<typeof schema>;

function userInitials(name: string): string {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]?.toUpperCase()).join('') || '?';
}

export function ProfilePage() {
  const { user, clear } = useAuth();
  const nav = useNavigate();
  const toast = useToasts((s) => s.push);

  const [showCurrent, setShowCurrent] = useState(false);
  const [showNew, setShowNew] = useState(false);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<Form>({
    defaultValues: { current_password: '', new_password: '', confirm_password: '' },
  });

  const change = useMutation({
    mutationFn: async (input: Form) => {
      await api.post('/auth/change-password', {
        current_password: input.current_password,
        new_password: input.new_password,
      });
    },
    onSuccess: () => {
      reset();
      toast({ tone: 'success', message: 'Password changed. Please sign in again.' });
      // The backend revokes other sessions; force a re-login here too.
      setTimeout(() => {
        clear();
        nav('/login', { replace: true });
      }, 1200);
    },
    onError: (e) => toast({ tone: 'danger', message: extractError(e).message }),
  });

  if (!user) return null;

  return (
    <div className="flex flex-col gap-6 max-w-3xl">
      <motion.header
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35 }}
      >
        <span className="label">Account</span>
        <h1 className="text-4xl font-semibold tracking-tight text-ink mt-1">Your profile</h1>
        <p className="text-sm text-ink-muted mt-1">
          Information about your account and security settings.
        </p>
      </motion.header>

      <Card>
        <div className="flex items-start gap-4">
          <span
            className="h-14 w-14 rounded-pill grid place-items-center text-white font-semibold text-lg shadow-glow"
            style={{ background: 'linear-gradient(135deg, #4F46E5, #6366F1, #8B5CF6)' }}
          >
            {userInitials(user.full_name)}
          </span>
          <div className="min-w-0 flex-1">
            <h2 className="text-xl font-semibold tracking-tight text-ink">{user.full_name}</h2>
            <p className="text-sm text-ink-muted flex items-center gap-1.5 mt-0.5">
              <Mail className="h-3.5 w-3.5" /> {user.email}
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              <Badge tone="assigned">{user.role.replace('_', ' ')}</Badge>
              {user.branch_id && (
                <span className="pill bg-info-soft text-info-deep">
                  <Building2 className="h-3.5 w-3.5" /> branch {user.branch_id.slice(0, 8)}
                </span>
              )}
              {user.mfa_enabled ? (
                <span className="pill bg-success-soft text-success-deep">
                  <ShieldCheck className="h-3.5 w-3.5" /> MFA enabled
                </span>
              ) : (
                <span className="pill bg-slate-100 text-ink-muted">
                  <Shield className="h-3.5 w-3.5" /> MFA disabled
                </span>
              )}
            </div>
          </div>
        </div>
      </Card>

      <Card>
        <h2 className="h-section flex items-center gap-2">
          <KeyRound className="h-4 w-4 text-brand-600" /> Change password
        </h2>
        <p className="text-sm text-ink-muted mt-1">
          Choose a strong password (≥ 8 characters). All other sessions will be signed out
          for safety.
        </p>

        <form
          className="mt-5 grid grid-cols-1 sm:grid-cols-2 gap-4"
          onSubmit={handleSubmit((v) => change.mutate(v))}
        >
          <div className="sm:col-span-2">
            <Field label="Current password" error={errors.current_password?.message}>
              <div className="relative">
                <input
                  className="input pr-11"
                  type={showCurrent ? 'text' : 'password'}
                  autoComplete="current-password"
                  {...register('current_password')}
                />
                <PwToggle
                  shown={showCurrent}
                  onToggle={() => setShowCurrent((v) => !v)}
                />
              </div>
            </Field>
          </div>

          <Field label="New password" error={errors.new_password?.message}>
            <div className="relative">
              <input
                className="input pr-11"
                type={showNew ? 'text' : 'password'}
                autoComplete="new-password"
                {...register('new_password')}
              />
              <PwToggle shown={showNew} onToggle={() => setShowNew((v) => !v)} />
            </div>
          </Field>

          <Field label="Confirm new password" error={errors.confirm_password?.message}>
            <input
              className="input"
              type={showNew ? 'text' : 'password'}
              autoComplete="new-password"
              {...register('confirm_password')}
            />
          </Field>

          <div className="sm:col-span-2 flex justify-end gap-2 mt-2">
            <button
              type="button"
              className="btn-secondary"
              onClick={() => reset()}
              disabled={isSubmitting}
            >
              Reset
            </button>
            <button type="submit" className="btn-primary" disabled={isSubmitting}>
              {isSubmitting ? 'Updating…' : 'Change password'}
            </button>
          </div>
        </form>
      </Card>
    </div>
  );
}

function Field({
  label,
  error,
  children,
}: {
  label: string;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="label">{label}</span>
      {children}
      {error && <span className="text-2xs text-danger-deep">{error}</span>}
    </label>
  );
}

function PwToggle({ shown, onToggle }: { shown: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-label={shown ? 'Hide password' : 'Show password'}
      aria-pressed={shown}
      className="absolute right-2 top-1/2 -translate-y-1/2 h-8 w-8 grid place-items-center rounded-pill text-ink-muted hover:text-ink hover:bg-white/70 transition-colors"
    >
      {shown ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
    </button>
  );
}
