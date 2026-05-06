import { api } from '@/lib/api';
import type { TicketDetail } from './types';

interface ItemEnvelope<T> { success: boolean; data: T }

export interface Comment {
  id: string;
  ticket_id: string;
  author_id: string;
  body: string;
  is_internal: boolean;
  created_at: string;
}

export interface AssignmentRow {
  id: string;
  ticket_id: string;
  assigned_to_user_id: string | null;
  assigned_to_team_id: string | null;
  assigned_by: string;
  assigned_at: string;
  unassigned_at: string | null;
  reason: string;
}

export interface Attachment {
  id: string;
  ticket_id: string;
  uploaded_by: string;
  file_name: string;
  mime_type: string;
  size_bytes: number;
  checksum_sha256: string;
  created_at: string;
}

const T = (id: string, action: string) => `/tickets/${id}/${action}`;

export const acknowledgeTicket = async (id: string) =>
  (await api.post<ItemEnvelope<TicketDetail>>(T(id, 'acknowledge'))).data.data;

export const assignTicket = async (
  id: string,
  body: { user_id?: string | null; team_id?: string | null; reason?: string },
) => (await api.post<ItemEnvelope<TicketDetail>>(T(id, 'assign'), body)).data.data;

export const startTicket = async (id: string) =>
  (await api.post<ItemEnvelope<TicketDetail>>(T(id, 'start'))).data.data;

export const holdTicket = async (id: string) =>
  (await api.post<ItemEnvelope<TicketDetail>>(T(id, 'hold'))).data.data;

export const escalateTicket = async (id: string, reason: string) =>
  (await api.post<ItemEnvelope<TicketDetail>>(T(id, 'escalate'), { reason })).data.data;

export const resolveTicket = async (id: string, notes: string) =>
  (await api.post<ItemEnvelope<TicketDetail>>(T(id, 'resolve'), { notes })).data.data;

export const closeTicket = async (id: string) =>
  (await api.post<ItemEnvelope<TicketDetail>>(T(id, 'close'))).data.data;

export const reopenTicket = async (id: string, reason: string) =>
  (await api.post<ItemEnvelope<TicketDetail>>(T(id, 'reopen'), { reason })).data.data;

export const listComments = async (id: string) =>
  (await api.get<{ data: Comment[] }>(T(id, 'comments'))).data.data;

export const postComment = async (id: string, body: string, isInternal: boolean) =>
  (await api.post<ItemEnvelope<Comment>>(T(id, 'comments'), { body, is_internal: isInternal })).data.data;

export const listAssignments = async (id: string) =>
  (await api.get<{ data: AssignmentRow[] }>(T(id, 'assignments'))).data.data;

export const listAttachments = async (id: string) =>
  (await api.get<{ data: Attachment[] }>(T(id, 'attachments'))).data.data;

export const uploadAttachment = async (id: string, file: File) => {
  const fd = new FormData();
  fd.append('file', file);
  const { data } = await api.post<ItemEnvelope<Attachment>>(T(id, 'attachments'), fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data.data;
};
