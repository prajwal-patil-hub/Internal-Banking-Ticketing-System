import { useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { ArrowLeft, Clock, MapPin, User as UserIcon } from 'lucide-react';

import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { getTicket } from '@/features/tickets/api';
import { PriorityBadge, StatusBadge } from '@/features/tickets/components/StatusBadge';
import { TicketActions } from '@/features/tickets/components/TicketActions';
import { CommentsThread } from '@/features/tickets/components/CommentsThread';
import { Attachments } from '@/features/tickets/components/Attachments';
import { AssignDialog } from '@/features/tickets/components/AssignDialog';
import { AssignmentHistory } from '@/features/tickets/components/AssignmentHistory';
import { formatDateTime, formatRelative, isBreached } from '@/lib/format';
import { useAuth } from '@/store/auth';
import { Skeleton } from '@/components/Skeleton';

export function TicketDetailPage() {
  const { id } = useParams();
  const { hasRole } = useAuth();
  const [assignOpen, setAssignOpen] = useState(false);

  const { data, isLoading, isError } = useQuery({
    queryKey: ['ticket', id],
    queryFn: () => getTicket(id!),
    enabled: !!id,
  });

  if (isLoading) {
    return (
      <div className="flex flex-col gap-6">
        <Skeleton className="h-7 w-40" />
        <Card><Skeleton className="h-32 w-full" /></Card>
      </div>
    );
  }
  if (isError || !data) {
    return <Card>Ticket not found.</Card>;
  }

  const canAssign = hasRole('admin', 'supervisor');

  return (
    <div className="flex flex-col gap-6">
      <Link to="/tickets" className="inline-flex items-center gap-1.5 text-sm text-ink-muted hover:text-ink w-fit">
        <ArrowLeft className="h-4 w-4" /> Back to tickets
      </Link>

      {/* Hero */}
      <motion.section
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35 }}
        className="glass rounded-4xl p-6 sm:p-7 relative overflow-hidden"
      >
        <div className="absolute -top-24 -right-24 h-64 w-64 rounded-full pointer-events-none"
             style={{ background: 'radial-gradient(circle, rgba(99,102,241,0.16), transparent 60%)' }} />
        <div className="relative z-10 flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-xs text-ink-muted">{data.ticket_no}</span>
              <span className="text-ink-subtle">·</span>
              <StatusBadge status={data.status} />
              <PriorityBadge priority={data.priority} />
              {data.sla_due_at && (
                <span
                  className="pill text-xs font-semibold"
                  style={{
                    background: isBreached(data.sla_due_at)
                      ? 'linear-gradient(135deg, rgba(239,68,68,0.18), rgba(248,113,113,0.10))'
                      : 'linear-gradient(135deg, rgba(16,185,129,0.18), rgba(52,211,153,0.10))',
                    color: isBreached(data.sla_due_at) ? '#DC2626' : '#059669',
                  }}
                >
                  <Clock className="h-3.5 w-3.5" />
                  SLA {formatRelative(data.sla_due_at)}
                </span>
              )}
            </div>
            <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight text-ink mt-3 leading-tight">
              {data.title}
            </h1>
            <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1.5 text-xs text-ink-muted">
              <span className="inline-flex items-center gap-1.5">
                <MapPin className="h-3.5 w-3.5" />
                Branch <code className="text-ink">{data.branch_id.slice(0, 8)}</code>
              </span>
              <span className="inline-flex items-center gap-1.5">
                <UserIcon className="h-3.5 w-3.5" />
                Raised by <code className="text-ink">{data.raised_by.slice(0, 8)}</code>
              </span>
              {data.assigned_user_id && (
                <span className="inline-flex items-center gap-1.5">
                  Assigned <code className="text-ink">{data.assigned_user_id.slice(0, 8)}</code>
                </span>
              )}
              <span className="text-ink-subtle">created {formatRelative(data.created_at)}</span>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {canAssign && (
              <button onClick={() => setAssignOpen(true)} className="btn-secondary">
                {data.assigned_user_id || data.assigned_team_id ? 'Re-assign' : 'Assign'}
              </button>
            )}
          </div>
        </div>
      </motion.section>

      {/* Body */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
        <div className="xl:col-span-2 flex flex-col gap-5">
          <Card>
            <h2 className="h-card mb-3">Description</h2>
            <p className="whitespace-pre-wrap text-sm text-ink leading-relaxed">{data.description}</p>
          </Card>

          <CommentsThread ticketId={data.id} />
        </div>

        <div className="flex flex-col gap-5">
          <TicketActions ticket={data} />
          <Attachments ticketId={data.id} />
          <AssignmentHistory ticketId={data.id} />

          <Card>
            <h3 className="h-card mb-3">Properties</h3>
            <dl className="text-sm space-y-2.5">
              <Row k="Branch ID"      v={<code className="text-2xs">{data.branch_id}</code>} />
              <Row k="Category ID"    v={<code className="text-2xs">{data.category_id}</code>} />
              <Row k="Raised by"      v={<code className="text-2xs">{data.raised_by}</code>} />
              <Row k="Assigned user"  v={data.assigned_user_id ? <code className="text-2xs">{data.assigned_user_id}</code> : '—'} />
              <Row k="Assigned team"  v={data.assigned_team_id ? <code className="text-2xs">{data.assigned_team_id}</code> : '—'} />
              <Row k="Reopened"       v={data.reopened_count} />
              <Row k="First response" v={formatDateTime(data.first_response_at)} />
              <Row k="Resolved"       v={formatDateTime(data.resolved_at)} />
              <Row k="Closed"         v={formatDateTime(data.closed_at)} />
              <Row k="Created"        v={formatDateTime(data.created_at)} />
              <Row k="Updated"        v={formatDateTime(data.updated_at)} />
            </dl>
          </Card>
        </div>
      </div>

      <AssignDialog ticket={data} open={assignOpen} onClose={() => setAssignOpen(false)} />
    </div>
  );
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-3 items-start">
      <dt className="text-ink-muted text-xs">{k}</dt>
      <dd className="text-right text-ink">{v}</dd>
    </div>
  );
}

