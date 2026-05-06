import { cn } from '@/lib/cn';

type Tone =
  | 'new' | 'ack' | 'assigned' | 'progress' | 'hold'
  | 'escalated' | 'resolved' | 'closed' | 'reopened'
  | 'neutral' | 'success' | 'warning' | 'danger' | 'info';

const toneClass: Record<Tone, string> = {
  new:        'bg-slate-100 text-slate-700',
  ack:        'bg-blue-100 text-blue-700',
  assigned:   'bg-violet-100 text-violet-700',
  progress:   'bg-sky-100 text-sky-700',
  hold:       'bg-amber-100 text-amber-700',
  escalated:  'bg-red-100 text-red-700',
  resolved:   'bg-emerald-100 text-emerald-700',
  closed:     'bg-slate-200 text-slate-800',
  reopened:   'bg-pink-100 text-pink-700',
  neutral:    'bg-slate-100 text-slate-700',
  success:    'bg-emerald-100 text-emerald-700',
  warning:    'bg-amber-100 text-amber-700',
  danger:     'bg-red-100 text-red-700',
  info:       'bg-blue-100 text-blue-700',
};

interface Props {
  tone?: Tone;
  className?: string;
  children: React.ReactNode;
}

export function Badge({ tone = 'neutral', className, children }: Props) {
  return <span className={cn('pill', toneClass[tone], className)}>{children}</span>;
}
