import { Badge } from '@/components/Badge';
import type { TicketStatus } from '@/features/tickets/api';

const STATUS_LABEL: Record<TicketStatus, string> = {
  new:          'New',
  acknowledged: 'Acknowledged',
  assigned:     'Assigned',
  in_progress:  'In Progress',
  on_hold:      'On Hold',
  escalated:    'Escalated',
  resolved:     'Resolved',
  closed:       'Closed',
  reopened:     'Reopened',
};

// Map each ticket status to an existing Badge tone
const STATUS_TONE: Record<TicketStatus, 'new' | 'ack' | 'assigned' | 'progress' | 'hold' | 'escalated' | 'resolved' | 'closed' | 'reopened'> = {
  new:          'new',
  acknowledged: 'ack',
  assigned:     'assigned',
  in_progress:  'progress',
  on_hold:      'hold',
  escalated:    'escalated',
  resolved:     'resolved',
  closed:       'closed',
  reopened:     'reopened',
};

interface Props {
  status: TicketStatus;
  className?: string;
}

export function StatusBadge({ status, className }: Props) {
  return (
    <Badge tone={STATUS_TONE[status]} className={className}>
      {STATUS_LABEL[status]}
    </Badge>
  );
}
