import { useNavigate } from 'react-router-dom';
import { StatusBadge } from '@/components/StatusBadge';
import { PriorityBadge } from '@/components/PriorityBadge';
import { SLABadge } from '@/components/SLABadge';
import { AIBadge } from '@/components/AIBadge';
import { cn } from '@/lib/cn';
import type { TicketSummary } from '@/features/tickets/api';

interface Props {
  ticket: TicketSummary & {
    department?: string | null;
    ai_category?: string | null;
    ai_confidence?: number | null;
    resolution_due_at?: string | null;
  };
  className?: string;
  /** Compact mode: single-line row layout used in dashboard feed */
  compact?: boolean;
}

function formatRelativeTime(dateStr: string): string {
  const date = new Date(dateStr).getTime();
  const now = Date.now();
  const diffMins = Math.floor((now - date) / 60_000);

  if (diffMins < 1) return 'just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  const hrs = Math.floor(diffMins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(dateStr).toLocaleDateString();
}

function SourceIcon({ source }: { source: string }) {
  const icons: Record<string, { path: string; label: string }> = {
    email:  { path: 'M4 4h16v16H4V4zm0 0l8 9 8-9', label: 'Email' },
    portal: { path: 'M12 2a10 10 0 1 0 0 20A10 10 0 0 0 12 2zM12 8v4l3 3', label: 'Portal' },
    phone:  { path: 'M22 16.9a15.9 15.9 0 0 1-5 1.1 16 16 0 0 1-16-16 15.9 15.9 0 0 1 1.1-5l3.5 3.5a2 2 0 0 0-.3 2.2L7 6a2 2 0 0 0 2.3-.3L12.6 9a2 2 0 0 0-.3 2.3l1.7 1.7a2 2 0 0 0 2.2-.3L16 12a2 2 0 0 0 2.3-.3l3.5 3.5z', label: 'Phone' },
    chat:   { path: 'M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v10z', label: 'Chat' },
    api:    { path: 'M4 17l6-6-6-6M12 19h8', label: 'API' },
  };
  const icon = icons[source] ?? icons.portal;
  return (
    <span title={icon.label} className="text-[var(--tx-3)]">
      <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
        <path d={icon.path} strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </span>
  );
}

export function TicketCard({ ticket, className, compact = false }: Props) {
  const navigate = useNavigate();

  /* ── Compact (dashboard feed) layout ── */
  if (compact) {
    return (
      <div
        role="button"
        tabIndex={0}
        onClick={() => navigate(`/tickets/${ticket.id}`)}
        onKeyDown={(e) => e.key === 'Enter' && navigate(`/tickets/${ticket.id}`)}
        className={cn(
          'card-sm cursor-pointer transition-shadow duration-150',
          '!p-0 flex items-center gap-3 px-3 py-2.5',
          'hover:shadow-[var(--neu-md)]',
          ticket.sla_breached && 'border-l-2 border-l-[var(--err)]',
          className,
        )}
      >
        {/* SLA dot */}
        <span className={cn(
          'h-2 w-2 rounded-full shrink-0',
          ticket.sla_breached ? 'bg-[var(--err)]' : 'bg-emerald-400',
        )} />

        {/* Ticket number */}
        <span className="font-mono text-[10px] font-bold text-brand-600 dark:text-brand-400 bg-brand-50 dark:bg-brand-900/30 px-1.5 py-0.5 rounded shrink-0">
          {ticket.ticket_number}
        </span>

        {/* Title */}
        <span className="flex-1 text-xs font-medium text-[var(--tx)] truncate">
          {ticket.title}
        </span>

        {/* Badges */}
        <div className="flex items-center gap-1.5 shrink-0">
          <StatusBadge status={ticket.status} />
          <PriorityBadge priority={ticket.priority} />
          <span className="text-[10px] text-[var(--tx-3)]">{formatRelativeTime(ticket.created_at)}</span>
        </div>
      </div>
    );
  }

  /* ── Standard card layout ── */
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => navigate(`/tickets/${ticket.id}`)}
      onKeyDown={(e) => e.key === 'Enter' && navigate(`/tickets/${ticket.id}`)}
      className={cn(
        'card-sm cursor-pointer transition-shadow duration-150',
        '!p-3.5 hover:shadow-[var(--neu-md)] hover:-translate-y-px',
        ticket.sla_breached && 'border-l-[3px] border-l-[var(--err)]',
        className,
      )}
    >
      <div className="flex items-start gap-2.5">
        <div className="flex-1 min-w-0">
          {/* Top row */}
          <div className="flex items-center gap-1.5 flex-wrap mb-1.5">
            <span className="font-mono text-[10px] font-bold text-brand-600 dark:text-brand-400 bg-brand-50 dark:bg-brand-900/30 px-1.5 py-0.5 rounded shrink-0">
              {ticket.ticket_number}
            </span>
            <StatusBadge status={ticket.status} />
            <PriorityBadge priority={ticket.priority} />
          </div>

          {/* Title */}
          <h3 className="text-sm font-medium text-[var(--tx)] line-clamp-2 leading-snug">
            {ticket.title}
          </h3>

          {/* AI info */}
          {(ticket.ai_category || ticket.ai_risk_score !== null) && (
            <div className="mt-1.5">
              <AIBadge
                category={ticket.ai_category ?? null}
                confidence={ticket.ai_confidence ?? null}
                riskScore={ticket.ai_risk_score}
                riskBand={ticket.ai_risk_band ?? null}
              />
            </div>
          )}

          {/* Bottom meta row */}
          <div className="mt-2 flex items-center gap-2.5 flex-wrap">
            <SLABadge breached={ticket.sla_breached} dueAt={ticket.resolution_due_at ?? null} />
            {ticket.department && (
              <span className="text-[11px] text-[var(--tx-2)]">{ticket.department}</span>
            )}
            <span className="text-[11px] text-[var(--tx-3)] ml-auto">
              {formatRelativeTime(ticket.created_at)}
            </span>
          </div>
        </div>

        {/* Source icon */}
        <div className="shrink-0 mt-0.5">
          <SourceIcon source={ticket.source} />
        </div>
      </div>
    </div>
  );
}
