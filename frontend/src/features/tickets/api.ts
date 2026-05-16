import { api } from '@/lib/api';

export type TicketStatus =
  | 'new'
  | 'acknowledged'
  | 'assigned'
  | 'in_progress'
  | 'on_hold'
  | 'escalated'
  | 'resolved'
  | 'closed'
  | 'reopened';

export type TicketPriority = 'critical' | 'high' | 'medium' | 'low';
export type TicketSource = 'email' | 'portal' | 'phone' | 'chat' | 'api';

export interface Ticket {
  id: string;
  ticket_number: string;
  title: string;
  description: string;
  status: TicketStatus;
  priority: TicketPriority;
  source: TicketSource;
  category_id: string | null;
  subcategory_id: string | null;
  reporter_id: string;
  assignee_id: string | null;
  branch_id: string | null;
  department: string | null;
  tags: string[];
  ai_category: string | null;
  ai_confidence: number | null;
  ai_summary: string | null;
  ai_risk_score: number | null;
  ai_sentiment: string | null;
  email_from: string | null;
  sla_breached: boolean;
  response_due_at: string | null;
  resolution_due_at: string | null;
  first_response_at: string | null;
  resolved_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface TicketSummary {
  id: string;
  ticket_number: string;
  title: string;
  status: TicketStatus;
  priority: TicketPriority;
  source: TicketSource;
  reporter_id: string;
  assignee_id: string | null;
  sla_breached: boolean;
  ai_risk_score: number | null;
  created_at: string;
}

export interface TicketCreate {
  title: string;
  description: string;
  priority: TicketPriority;
  category_id?: string;
  tags?: string[];
}

export interface Comment {
  id: string;
  ticket_id: string;
  author_id: string | null;
  body: string;
  is_internal: boolean;
  source: string;
  ai_generated: boolean;
  created_at: string;
}

export interface Category {
  id: string;
  code: string;
  name: string;
  department: string;
  banking_domain: string;
}

export interface AuditEntry {
  id: string;
  entity_type: string;
  entity_id: string;
  action: string;
  actor_id: string | null;
  actor_email: string | null;
  old_values: Record<string, unknown> | null;
  new_values: Record<string, unknown> | null;
  ip_address: string | null;
  created_at: string;
}

export interface TicketListParams {
  status?: TicketStatus;
  priority?: TicketPriority;
  assignee_id?: string;
  search?: string;
  page?: number;
  page_size?: number;
  my_tickets?: boolean;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

function unwrapPaginated<T>(body: {
  data: T[];
  meta?: { pagination?: { page: number; size: number; total: number; pages: number } };
}): PaginatedResponse<T> {
  const p = body.meta?.pagination ?? { page: 1, size: 0, total: 0, pages: 0 };
  return {
    items: body.data ?? [],
    total: p.total,
    page: p.page,
    page_size: p.size,
    total_pages: p.pages,
  };
}

export async function listTickets(params?: TicketListParams): Promise<PaginatedResponse<TicketSummary>> {
  const { page_size, ...rest } = params ?? {};
  const apiParams = { ...rest, ...(page_size != null ? { per_page: page_size } : {}) };
  const { data } = await api.get('/tickets', { params: apiParams });
  return unwrapPaginated<TicketSummary>(data);
}

export async function getTicket(id: string): Promise<Ticket> {
  const { data } = await api.get(`/tickets/${id}`);
  return data.data;
}

export async function getTicketByNumber(number: string): Promise<Ticket> {
  const { data } = await api.get(`/tickets/number/${number}`);
  return data.data;
}

export async function createTicket(payload: TicketCreate): Promise<Ticket> {
  const { data } = await api.post('/tickets', payload);
  return data.data;
}

export async function updateTicketStatus(
  id: string,
  status: TicketStatus,
  reason?: string,
): Promise<Ticket> {
  const { data } = await api.post(`/tickets/${id}/status`, { status, reason });
  return data.data;
}

export async function assignTicket(id: string, assignee_id: string): Promise<Ticket> {
  const { data } = await api.post(`/tickets/${id}/assign`, { assignee_id });
  return data.data;
}

export async function getComments(ticketId: string): Promise<Comment[]> {
  const { data } = await api.get(`/tickets/${ticketId}/comments`);
  return data.data;
}

export async function addComment(
  ticketId: string,
  body: string,
  is_internal = false,
): Promise<Comment> {
  const { data } = await api.post(`/tickets/${ticketId}/comments`, { body, is_internal });
  return data.data;
}

export async function getCategories(): Promise<Category[]> {
  const { data } = await api.get('/categories');
  return data.data;
}

export async function aiSummarize(ticketId: string): Promise<{ summary: string; sentiment: string; risk_score: number }> {
  const { data } = await api.post(`/tickets/${ticketId}/ai-summarize`);
  return data.data;
}

export async function aiSuggest(ticketId: string): Promise<{ suggestions: string[]; next_actions: string[] }> {
  const { data } = await api.post(`/tickets/${ticketId}/ai-suggest`);
  return data.data;
}

export async function pauseSLA(ticketId: string, _reason?: string): Promise<Ticket> {
  const { data } = await api.post(`/tickets/${ticketId}/pause-sla`);
  return data.data;
}

export async function resumeSLA(ticketId: string): Promise<Ticket> {
  const { data } = await api.post(`/tickets/${ticketId}/resume-sla`);
  return data.data;
}

export async function getAuditLog(params?: {
  entity_type?: string;
  action?: string;
  from_date?: string;
  to_date?: string;
  page?: number;
  page_size?: number;
}): Promise<PaginatedResponse<AuditEntry>> {
  const { page_size, ...rest } = params ?? {};
  const apiParams = { ...rest, ...(page_size != null ? { per_page: page_size } : {}) };
  const { data } = await api.get('/audit', { params: apiParams });
  return unwrapPaginated<AuditEntry>(data);
}
