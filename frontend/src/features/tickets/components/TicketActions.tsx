import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Check, Play, Pause, AlertTriangle, CheckCircle2, Lock, RotateCcw,
} from 'lucide-react';

import { Card } from '@/components/Card';
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
      <h3 className="h-card">Actions</h3>
      {!anyAvailable && (
        <p className="mt-2 text-sm text-ink-muted">No actions available for your role at this status.</p>
      )}

      {error && <Badge tone="danger" className="mt-3">{error}</Badge>}

      {reasonOpen ? (
        <div className="mt-4 space-y-2">
          <textarea
            className="input min-h-[100px] resize-y"
            placeholder={
              reasonOpen === 'resolve' ? 'Resolution notes (visible to branch user)…'
              : reasonOpen === 'reopen' ? 'Why are you reopening this ticket?'
              : 'Why are you escalating?'
            }
            value={reasonText}
            onChange={(e) => setReasonText(e.target.value)}
          />
          <div className="flex justify-end gap-2">
            <button className="btn-secondary" onClick={() => { setReasonOpen(null); setReasonText(''); }}>
              Cancel
            </button>
            <button
              className="btn-primary"
              onClick={() => {
                if (reasonOpen === 'resolve') resolve.mutate();
                else if (reasonOpen === 'reopen') reopen.mutate();
                else escalate.mutate();
              }}
            >
              Confirm
            </button>
          </div>
        </div>
      ) : (
        <div className="mt-4 grid grid-cols-2 gap-2">
          {can.ack      && <ActionBtn icon={<Check className="h-4 w-4" />}        onClick={() => ack.mutate()}>Acknowledge</ActionBtn>}
          {can.start    && <ActionBtn icon={<Play className="h-4 w-4" />}         onClick={() => start.mutate()}>Start work</ActionBtn>}
          {can.hold     && <ActionBtn icon={<Pause className="h-4 w-4" />}        onClick={() => hold.mutate()}>Put on hold</ActionBtn>}
          {can.escalate && <ActionBtn icon={<AlertTriangle className="h-4 w-4" />} onClick={() => { setError(null); setReasonOpen('escalate'); }}>Escalate…</ActionBtn>}
          {can.resolve  && <ActionBtn icon={<CheckCircle2 className="h-4 w-4" />}  onClick={() => { setError(null); setReasonOpen('resolve'); }} primary>Resolve…</ActionBtn>}
          {can.close    && <ActionBtn icon={<Lock className="h-4 w-4" />}          onClick={() => close_.mutate()} primary>Close</ActionBtn>}
          {can.reopen   && <ActionBtn icon={<RotateCcw className="h-4 w-4" />}     onClick={() => { setError(null); setReasonOpen('reopen'); }}>Reopen…</ActionBtn>}
        </div>
      )}
    </Card>
  );
}

function ActionBtn({
  icon,
  onClick,
  primary,
  children,
}: {
  icon: React.ReactNode;
  onClick: () => void;
  primary?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button onClick={onClick} className={primary ? 'btn-primary' : 'btn-secondary'}>
      {icon}
      <span>{children}</span>
    </button>
  );
}
