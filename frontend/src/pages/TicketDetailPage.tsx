import { useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';

import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { Button } from '@/components/Button';
import { getTicket } from '@/features/tickets/api';
import { PriorityBadge, StatusBadge } from '@/features/tickets/components/StatusBadge';
import { TicketActions } from '@/features/tickets/components/TicketActions';
import { CommentsThread } from '@/features/tickets/components/CommentsThread';
import { Attachments } from '@/features/tickets/components/Attachments';
import { AssignDialog } from '@/features/tickets/components/AssignDialog';
import { AssignmentHistory } from '@/features/tickets/components/AssignmentHistory';
import { formatDateTime, formatRelative, isBreached } from '@/lib/format';
import { useAuth } from '@/store/auth';

export function TicketDetailPage() {
  const { id } = useParams();
  const { hasRole } = useAuth();
  const [assignOpen, setAssignOpen] = useState(false);

  const { data, isLoading, isError } = useQuery({
    queryKey: ['ticket', id],
    queryFn: () => getTicket(id!),
    enabled: !!id,
  });

  if (isLoading) return <Card>Loading…</Card>;
  if (isError || !data) return <Card>Ticket not found.</Card>;

  const canAssign = hasRole('admin', 'supervisor');

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center gap-3 flex-wrap">
        <Link to="/tickets" className="btn-ghost">← Back</Link>
        <h1 className="text-2xl font-semibold tracking-tight">{data.ticket_no}</h1>
        <StatusBadge status={data.status} />
        <PriorityBadge priority={data.priority} />
        {data.sla_due_at && (
          <Badge tone={isBreached(data.sla_due_at) ? 'danger' : 'success'}>
            SLA {formatRelative(data.sla_due_at)}
          </Badge>
        )}
        <div className="ml-auto flex items-center gap-2">
          {canAssign && (
            <Button variant="ghost" onClick={() => setAssignOpen(true)}>
              {data.assigned_user_id || data.assigned_team_id ? 'Re-assign' : 'Assign'}
            </Button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <div className="xl:col-span-2 flex flex-col gap-6">
          <Card>
            <h2 className="text-lg font-semibold">{data.title}</h2>
            <p className="mt-3 whitespace-pre-wrap text-sm text-slate-700 dark:text-slate-300">{data.description}</p>
          </Card>

          <CommentsThread ticketId={data.id} />
        </div>

        <div className="flex flex-col gap-6">
          <TicketActions ticket={data} />
          <Attachments ticketId={data.id} />
          <AssignmentHistory ticketId={data.id} />

          <Card>
            <h3 className="font-semibold">Properties</h3>
            <dl className="mt-3 text-sm space-y-2">
              <Row k="Branch ID"      v={<code className="text-xs">{data.branch_id}</code>} />
              <Row k="Category ID"    v={<code className="text-xs">{data.category_id}</code>} />
              <Row k="Raised by"      v={<code className="text-xs">{data.raised_by}</code>} />
              <Row k="Assigned user"  v={data.assigned_user_id ? <code className="text-xs">{data.assigned_user_id}</code> : '—'} />
              <Row k="Assigned team"  v={data.assigned_team_id ? <code className="text-xs">{data.assigned_team_id}</code> : '—'} />
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
    <div className="flex justify-between gap-3">
      <dt className="text-slate-500">{k}</dt>
      <dd className="text-right">{v}</dd>
    </div>
  );
}
