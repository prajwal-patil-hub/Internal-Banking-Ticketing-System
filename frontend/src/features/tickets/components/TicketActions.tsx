import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';

import { Card } from '@/components/Card';
import { Button } from '@/components/Button';
import { Badge } from '@/components/Badge';
import { useToasts } from '@/components/Toast';
import { useAuth } from '@/store/auth';
import { extractError } from '@/lib/api';
import type { TicketDetail } from '../types';
import {
  acknowledgeTicket, closeTicket, escalateTicket,
  holdTicket, reopenTicket, resolveTicket, startTicket,
} from '../workflow';

interface Props { ticket: TicketDetail }

export function TicketActions({ ticket }: Props) {
  const qc = useQueryClient();
  const { hasRole } = useAuth();
  const toast = useToasts((s) => s.push);
  const [reasonOpen, setReasonOpen] = useState<null | 'escalate' | 'resolve' | 'reopen'>(null);
  const [reasonText, setReasonText] = useState('');
  const [error, setError] = useState<string | null>(null);

  const onSuccess = (msg: string) => () => {
    qc.invalidateQueries({ queryKey: ['ticket', ticket.id] });
    toast({ tone: 'success', message: msg });
  };
  const onError = (e: unknown) => {
    const m = extractError(e).message;
    setError(m);
    toast({ tone: 'danger', message: m });
  };

  const ack    = useMutation({ mutationFn: () => acknowledgeTicket(ticket.id), onSuccess: onSuccess('Ticket acknowledged.'), onError });
  const start  = useMutation({ mutationFn: () => startTicket(ticket.id),       onSuccess: onSuccess('Work started.'),         onError });
  const hold   = useMutation({ mutationFn: () => holdTicket(ticket.id),         onSuccess: onSuccess('Ticket on hold (SLA paused).'), onError });
  const close_ = useMutation({ mutationFn: () => closeTicket(ticket.id),        onSuccess: onSuccess('Ticket closed.'),        onError });

  const escalate = useMutation({
    mutationFn: () => escalateTicket(ticket.id, reasonText),
    onSuccess: () => { setReasonOpen(null); setReasonText(''); onSuccess('Escalation raised.')(); },
    onError,
  });
  const resolve = useMutation({
    mutationFn: () => resolveTicket(ticket.id, reasonText),
    onSuccess: () => { setReasonOpen(null); setReasonText(''); onSuccess('Ticket resolved.')(); },
    onError,
  });
  const reopen = useMutation({
    mutationFn: () => reopenTicket(ticket.id, reasonText),
    onSuccess: () => { setReasonOpen(null); setReasonText(''); onSuccess('Ticket reopened (SLA reset).')(); },
    onError,
  });

  const isAdmin       = hasRole('admin');
  const isAgent       = hasRole('agent');
  const isSupervisor  = hasRole('supervisor');
  const isBranchUser  = hasRole('branch_user');

  const s = ticket.status;

  // Visibility map keeps the JSX readable.
  const can = {
    ack:      isAdmin && s === 'new',
    start:    (isAgent || isSupervisor) && (s === 'acknowledged' || s === 'assigned' || s === 'on_hold' || s === 'escalated' || s === 'reopened'),
    hold:     (isAgent || isSupervisor) && (s === 'assigned' || s === 'in_progress'),
    escalate: (isAgent || isSupervisor) && (s === 'assigned' || s === 'in_progress' || s === 'on_hold'),
    resolve:  (isAgent || isSupervisor) && (s === 'in_progress' || s === 'escalated'),
    close:    isAdmin && s === 'resolved',
    reopen:   (isBranchUser || isAdmin) && (s === 'resolved' || s === 'closed'),
  };

  const anyAvailable = Object.values(can).some(Boolean);

  return (
    <Card>
      <h3 className="font-semibold">Actions</h3>
      {!anyAvailable && (
        <p className="mt-2 text-sm text-slate-500">No actions available for your role at this status.</p>
      )}

      {error && <Badge tone="danger" className="mt-3">{error}</Badge>}

      {reasonOpen && (
        <div className="mt-4 space-y-2">
          <textarea
            className="input min-h-[90px]"
            placeholder={
              reasonOpen === 'resolve' ? 'Resolution notes (visible to branch user)…'
              : reasonOpen === 'reopen' ? 'Why are you reopening this ticket?'
              : 'Why are you escalating?'
            }
            value={reasonText}
            onChange={e => setReasonText(e.target.value)}
          />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => { setReasonOpen(null); setReasonText(''); }}>Cancel</Button>
            <Button onClick={() => {
              if (reasonOpen === 'resolve') resolve.mutate();
              else if (reasonOpen === 'reopen') reopen.mutate();
              else escalate.mutate();
            }}>
              Confirm
            </Button>
          </div>
        </div>
      )}

      {!reasonOpen && (
        <div className="mt-3 grid grid-cols-2 gap-2">
          {can.ack      && <Button variant="ghost" onClick={() => ack.mutate()}>Acknowledge</Button>}
          {can.start    && <Button variant="ghost" onClick={() => start.mutate()}>Start work</Button>}
          {can.hold     && <Button variant="ghost" onClick={() => hold.mutate()}>Put on hold</Button>}
          {can.escalate && <Button variant="ghost" onClick={() => { setError(null); setReasonOpen('escalate'); }}>Escalate…</Button>}
          {can.resolve  && <Button onClick={() => { setError(null); setReasonOpen('resolve'); }}>Resolve…</Button>}
          {can.close    && <Button onClick={() => close_.mutate()}>Close</Button>}
          {can.reopen   && <Button variant="ghost" onClick={() => { setError(null); setReasonOpen('reopen'); }}>Reopen…</Button>}
        </div>
      )}
    </Card>
  );
}
