import { cn } from '@/lib/cn';
import type { TicketPriority } from '@/features/tickets/api';

const PRIORITY_LABEL: Record<TicketPriority, string> = {
  critical: 'Critical',
  high:     'High',
  medium:   'Medium',
  low:      'Low',
};

const PRIORITY_CLASS: Record<TicketPriority, string> = {
  critical: 'bg-red-100 text-red-700',
  high:     'bg-orange-100 text-orange-700',
  medium:   'bg-amber-100 text-amber-700',
  low:      'bg-slate-100 text-slate-600',
};

interface Props {
  priority: TicketPriority;
  className?: string;
}

export function PriorityBadge({ priority, className }: Props) {
  return (
    <span className={cn('pill', PRIORITY_CLASS[priority], className)}>
      {PRIORITY_LABEL[priority]}
    </span>
  );
}
