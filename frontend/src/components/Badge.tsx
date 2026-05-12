import { cn } from '@/lib/cn';

type Tone =
  | 'new' | 'ack' | 'assigned' | 'progress' | 'hold'
  | 'escalated' | 'resolved' | 'closed' | 'reopened'
  | 'neutral' | 'success' | 'warning' | 'danger' | 'info' | 'brass';

// Old-money soft pills — translucent fills, deep ink type.
const toneClass: Record<Tone, string> = {
  new:        'bg-info-soft text-info-deep',
  ack:        'bg-info-soft text-info-deep',
  assigned:   'bg-brand-50 text-brand-700',
  progress:   'bg-warning-soft text-warning-deep',
  hold:       'bg-warning-soft text-warning-deep',
  escalated:  'bg-danger-soft text-danger-deep',
  resolved:   'bg-success-soft text-success-deep',
  closed:     'bg-canvas-alt text-ink-muted',
  reopened:   'bg-accent-50 text-accent-500',
  neutral:    'bg-canvas-alt text-ink-muted',
  success:    'bg-success-soft text-success-deep',
  warning:    'bg-warning-soft text-warning-deep',
  danger:     'bg-danger-soft text-danger-deep',
  info:       'bg-info-soft text-info-deep',
  brass:      'bg-brass-soft text-brass-600',
};

interface Props {
  tone?: Tone;
  className?: string;
  children: React.ReactNode;
}

export function Badge({ tone = 'neutral', className, children }: Props) {
  return <span className={cn('pill', toneClass[tone], className)}>{children}</span>;
}
