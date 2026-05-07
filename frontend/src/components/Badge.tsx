import { cn } from '@/lib/cn';

type Tone =
  | 'new' | 'ack' | 'assigned' | 'progress' | 'hold'
  | 'escalated' | 'resolved' | 'closed' | 'reopened'
  | 'neutral' | 'success' | 'warning' | 'danger' | 'info';

/**
 * Soft tinted status pill. Each tone is a translucent colored fill with a
 * deep text colour — readable on any glass surface.
 */
const toneClass: Record<Tone, string> = {
  new:        'bg-info-soft text-info-deep',
  ack:        'bg-info-soft text-info-deep',
  assigned:   'bg-accent-100 text-accent-500',
  progress:   'bg-warning-soft text-warning-deep',
  hold:       'bg-warning-soft text-warning-deep',
  escalated:  'bg-danger-soft text-danger-deep',
  resolved:   'bg-success-soft text-success-deep',
  closed:     'bg-slate-200/70 text-slate-700',
  reopened:   'bg-pink-100 text-pink-700',
  neutral:    'bg-slate-100/80 text-slate-700',
  success:    'bg-success-soft text-success-deep',
  warning:    'bg-warning-soft text-warning-deep',
  danger:     'bg-danger-soft text-danger-deep',
  info:       'bg-info-soft text-info-deep',
};

interface Props {
  tone?: Tone;
  className?: string;
  children: React.ReactNode;
}

export function Badge({ tone = 'neutral', className, children }: Props) {
  return <span className={cn('pill', toneClass[tone], className)}>{children}</span>;
}
