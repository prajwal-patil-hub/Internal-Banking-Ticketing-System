import { cn } from '@/lib/cn';
import type { TicketPriority } from '@/features/tickets/api';

const PRIORITY_LABEL: Record<TicketPriority, string> = {
  critical: 'Critical',
  high:     'High',
  medium:   'Medium',
  low:      'Low',
};

const PRIORITY_CLASS: Record<TicketPriority, string> = {
  critical: 'pill-err',
  high:     'bg-orange-100 text-orange-700 dark:bg-orange-900/20 dark:text-orange-400',
  medium:   'pill-warn',
  low:      'pill-neu',
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
