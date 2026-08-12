import { cn } from '@/lib/cn';

type Tone =
  | 'new' | 'ack' | 'assigned' | 'progress' | 'hold'
  | 'escalated' | 'resolved' | 'closed' | 'reopened'
  | 'neutral' | 'success' | 'warning' | 'danger' | 'info';

const toneClass: Record<Tone, string> = {
  new:        'bg-status-new/10 text-status-new',
  ack:        'bg-status-ack/10 text-status-ack',
  assigned:   'bg-status-assigned/10 text-status-assigned',
  progress:   'bg-status-progress/10 text-status-progress',
  hold:       'bg-status-hold/10 text-status-hold',
  escalated:  'bg-status-escalated/10 text-status-escalated',
  resolved:   'bg-status-resolved/10 text-status-resolved',
  closed:     'bg-status-closed/10 text-status-closed',
  reopened:   'bg-status-reopened/10 text-status-reopened',
  neutral:    'pill-neu',
  success:    'pill-ok',
  warning:    'pill-warn',
  danger:     'pill-err',
  info:       'pill-info',
};

interface Props {
  tone?: Tone;
  className?: string;
  children: React.ReactNode;
}

export function Badge({ tone = 'neutral', className, children }: Props) {
  return <span className={cn('pill', toneClass[tone], className)}>{children}</span>;
}
