import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { Modal } from '@/components/Modal';
import { Button } from '@/components/Button';
import { Badge } from '@/components/Badge';
import { api, extractError } from '@/lib/api';
import { useAuth } from '@/store/auth';
import { assignTicket } from '../workflow';
import type { TicketDetail } from '../types';

interface UserRow { id: string; email: string; full_name: string; role: string }
interface TeamRow { id: string; name: string }

interface ListEnvelope<T> { data: T[] }

async function listAgents() {
  const { data } = await api.get<ListEnvelope<UserRow>>('/users?page=1&size=100');
  return data.data.filter((u) => ['agent', 'supervisor'].includes(u.role));
}
async function listTeams() {
  const { data } = await api.get<ListEnvelope<TeamRow>>('/teams?page=1&size=100');
  return data.data;
}

interface Props {
  ticket: TicketDetail;
  open: boolean;
  onClose: () => void;
}

export function AssignDialog({ ticket, open, onClose }: Props) {
  const qc = useQueryClient();
  const { hasRole } = useAuth();
  const enabled = open && hasRole('admin', 'supervisor');

  const [userId, setUserId] = useState<string>(ticket.assigned_user_id ?? '');
  const [teamId, setTeamId] = useState<string>(ticket.assigned_team_id ?? '');
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);

  const agents = useQuery({ queryKey: ['agents'], queryFn: listAgents, enabled });
  const teams  = useQuery({ queryKey: ['teams'],  queryFn: listTeams,  enabled });

  const submit = useMutation({
    mutationFn: () => assignTicket(ticket.id, {
      user_id: userId || null,
      team_id: teamId || null,
      reason,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['ticket', ticket.id] });
      qc.invalidateQueries({ queryKey: ['assignments', ticket.id] });
      onClose();
    },
    onError: (e) => setError(extractError(e).message),
  });

  return (
    <Modal open={open} onClose={onClose} title="Assign ticket">
      {error && <Badge tone="danger" className="mb-3">{error}</Badge>}
      <div className="grid grid-cols-1 gap-3">
        <label className="text-sm">
          <span className="block mb-1 font-medium">Assign to user</span>
          <select className="input" value={userId} onChange={(e) => setUserId(e.target.value)}>
            <option value="">(none)</option>
            {agents.data?.map((u) => (
              <option key={u.id} value={u.id}>{u.full_name} — {u.role}</option>
            ))}
          </select>
        </label>

        <label className="text-sm">
          <span className="block mb-1 font-medium">Assign to team</span>
          <select className="input" value={teamId} onChange={(e) => setTeamId(e.target.value)}>
            <option value="">(none)</option>
            {teams.data?.map((t) => (
              <option key={t.id} value={t.id}>{t.name}</option>
            ))}
          </select>
        </label>

        <label className="text-sm">
          <span className="block mb-1 font-medium">Reason (optional)</span>
          <input className="input" value={reason} onChange={(e) => setReason(e.target.value)} />
        </label>

        <div className="flex justify-end gap-2 mt-2">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button disabled={submit.isPending || (!userId && !teamId)} onClick={() => { setError(null); submit.mutate(); }}>
            {submit.isPending ? 'Saving…' : 'Save assignment'}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
