import { Badge } from '@/components/Badge';
import type { Priority, TicketStatus } from '../types';

const STATUS_TONE: Record<TicketStatus, Parameters<typeof Badge>[0]['tone']> = {
  new: 'new',
  acknowledged: 'ack',
  assigned: 'assigned',
  in_progress: 'progress',
  on_hold: 'hold',
  escalated: 'escalated',
  resolved: 'resolved',
  closed: 'closed',
  reopened: 'reopened',
};

const PRIORITY_TONE: Record<Priority, Parameters<typeof Badge>[0]['tone']> = {
  critical: 'danger',
  high: 'warning',
  medium: 'info',
  low: 'neutral',
};

const STATUS_LABEL: Record<TicketStatus, string> = {
  new: 'New',
  acknowledged: 'Acknowledged',
  assigned: 'Assigned',
  in_progress: 'In progress',
  on_hold: 'On hold',
  escalated: 'Escalated',
  resolved: 'Resolved',
  closed: 'Closed',
  reopened: 'Reopened',
};

const STATUS_DOT: Record<TicketStatus, string> = {
  new:          'bg-info',
  acknowledged: 'bg-info',
  assigned:     'bg-accent-500',
  in_progress:  'bg-warning',
  on_hold:      'bg-warning',
  escalated:    'bg-danger',
  resolved:     'bg-success',
  closed:       'bg-slate-500',
  reopened:     'bg-pink-500',
};

export function StatusBadge({ status }: { status: TicketStatus }) {
  return (
    <Badge tone={STATUS_TONE[status]}>
      <span className={`h-1.5 w-1.5 rounded-pill ${STATUS_DOT[status]}`} aria-hidden />
      {STATUS_LABEL[status]}
    </Badge>
  );
}

export function PriorityBadge({ priority }: { priority: Priority }) {
  return <Badge tone={PRIORITY_TONE[priority]}>{priority}</Badge>;
}
