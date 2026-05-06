import { api } from '@/lib/api';

export interface NotificationItem {
  id: string;
  user_id: string;
  channel: string;
  type: string;
  subject: string;
  body: string;
  payload: Record<string, unknown>;
  status: string;
  sent_at: string | null;
  read_at: string | null;
  created_at: string;
}

interface ListEnvelope<T> {
  data: T[];
  meta: { pagination: { page: number; size: number; total: number; pages: number } };
}

export async function listNotifications(opts: { unread?: boolean; page?: number; size?: number } = {}) {
  const params = new URLSearchParams();
  if (opts.unread) params.set('unread', 'true');
  params.set('page', String(opts.page ?? 1));
  params.set('size', String(opts.size ?? 20));
  const { data } = await api.get<ListEnvelope<NotificationItem>>(`/notifications?${params.toString()}`);
  return { items: data.data, meta: data.meta.pagination };
}

export async function unreadCount(): Promise<number> {
  const { data } = await api.get<{ data: { unread: number } }>('/notifications/unread-count');
  return data.data.unread;
}

export async function markRead(id: string): Promise<NotificationItem> {
  const { data } = await api.post<{ data: NotificationItem }>(`/notifications/${id}/read`);
  return data.data;
}
