import { api } from '@/lib/api';
import type { Branch, Category, Priority, TicketDetail, TicketStatus, TicketSummary } from './types';

interface PaginationMeta {
  page: number; size: number; total: number; pages: number;
}
interface ListEnvelope<T> {
  success: boolean;
  data: T[];
  meta: { pagination: PaginationMeta };
}
interface ItemEnvelope<T> { success: boolean; data: T; }

export interface TicketFilters {
  page?: number;
  size?: number;
  status?: TicketStatus[];
  priority?: Priority[];
  branch_id?: string;
  assigned_user_id?: string;
  breached?: boolean;
  q?: string;
  date_from?: string;
  date_to?: string;
  /** e.g. "-created_at", "priority", "-sla_due_at" */
  sort?: string;
}

export async function listTickets(f: TicketFilters = {}) {
  const params = new URLSearchParams();
  if (f.page) params.set('page', String(f.page));
  if (f.size) params.set('size', String(f.size));
  f.status?.forEach((s) => params.append('status', s));
  f.priority?.forEach((p) => params.append('priority', p));
  if (f.branch_id) params.set('branch_id', f.branch_id);
  if (f.assigned_user_id) params.set('assigned_user_id', f.assigned_user_id);
  if (f.breached != null) params.set('breached', String(f.breached));
  if (f.q) params.set('q', f.q);
  if (f.date_from) params.set('date_from', f.date_from);
  if (f.date_to) params.set('date_to', f.date_to);
  if (f.sort) params.set('sort', f.sort);

  const { data } = await api.get<ListEnvelope<TicketSummary>>(`/tickets?${params.toString()}`);
  return { items: data.data, meta: data.meta.pagination };
}

export async function getTicket(id: string) {
  const { data } = await api.get<ItemEnvelope<TicketDetail>>(`/tickets/${id}`);
  return data.data;
}

export interface CreateTicketInput {
  branch_id: string;
  category_id: string;
  title: string;
  description: string;
  priority: Priority;
}

export async function createTicket(input: CreateTicketInput) {
  const { data } = await api.post<ItemEnvelope<TicketDetail>>('/tickets', input);
  return data.data;
}

export async function listBranches(page = 1, size = 100, includeInactive = false) {
  const params = new URLSearchParams({ page: String(page), size: String(size) });
  if (includeInactive) params.set('include_inactive', 'true');
  const { data } = await api.get<ListEnvelope<Branch>>(`/branches?${params.toString()}`);
  return { items: data.data, meta: data.meta.pagination };
}

export async function listCategories() {
  const { data } = await api.get<ListEnvelope<Category>>('/categories?page=1&size=100');
  return data.data;
}
