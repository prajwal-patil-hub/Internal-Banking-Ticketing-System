import { cn } from '@/lib/cn';

type Tone =
  | 'new' | 'ack' | 'assigned' | 'progress' | 'hold'
  | 'escalated' | 'resolved' | 'closed' | 'reopened'
  | 'neutral' | 'success' | 'warning' | 'danger' | 'info';

// Light variant for light mode + dark variant overrides for dark mode so
// pills stay readable against slate-900 backgrounds.
const toneClass: Record<Tone, string> = {
  new:        'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200',
  ack:        'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-200',
  assigned:   'bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-200',
  progress:   'bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-200',
  hold:       'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-200',
  escalated:  'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-200',
  resolved:   'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-200',
  closed:     'bg-slate-200 text-slate-800 dark:bg-slate-700 dark:text-slate-100',
  reopened:   'bg-pink-100 text-pink-700 dark:bg-pink-900/40 dark:text-pink-200',
  neutral:    'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200',
  success:    'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-200',
  warning:    'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-200',
  danger:     'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-200',
  info:       'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-200',
};

interface Props {
  tone?: Tone;
  className?: string;
  children: React.ReactNode;
}

export function Badge({ tone = 'neutral', className, children }: Props) {
  return <span className={cn('pill', toneClass[tone], className)}>{children}</span>;
}
