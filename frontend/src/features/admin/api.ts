import { api } from '@/lib/api';

export interface AdminUser {
  id: string;
  email: string;
  full_name: string;
  role: string;
  branch_id: string | null;
  is_active: boolean;
  mfa_enabled: boolean;
  last_login_at: string | null;
  created_at: string;
}

export interface RoleSummary {
  id: string;
  name: string;
  description: string;
  permissions: string[];
}

export interface Branch {
  id: string;
  code: string;
  name: string;
  region: string;
  address: string;
  ifsc: string;
  contact_email: string;
  contact_phone: string;
  is_active: boolean;
  created_at: string;
}

export interface EscalationRule {
  id: string;
  name: string;
  trigger: string;
  trigger_after_minutes: number | null;
  escalate_to_role: string;
  escalate_to_user_id: string | null;
  notify_email: string | null;
  category_id: string | null;
  priority_threshold: string | null;
  is_active: boolean;
  created_at: string;
}

export interface EscalationEvent {
  id: string;
  ticket_id: string;
  rule_id: string | null;
  rule_name: string | null;
  trigger: string;
  triggered_at: string;
  escalated_to_id: string | null;
  escalated_to_email: string | null;
  escalated_by_id: string | null;
  escalated_by_email: string | null;
  reason: string | null;
  resolved_at: string | null;
}

interface ListResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

function unwrapPaginated<T>(body: {
  data: T[];
  meta?: { pagination?: { page: number; size: number; total: number; pages: number } };
}): ListResponse<T> {
  const p = body.meta?.pagination ?? { page: 1, size: 0, total: 0, pages: 0 };
  return {
    items: body.data ?? [],
    total: p.total,
    page: p.page,
    page_size: p.size,
    total_pages: p.pages,
  };
}

export async function listUsers(params?: {
  page?: number;
  per_page?: number;
  search?: string;
  role?: string;
  is_active?: boolean;
}): Promise<ListResponse<AdminUser>> {
  const { data } = await api.get('/users', { params });
  return unwrapPaginated<AdminUser>(data);
}

export async function listRoles(): Promise<RoleSummary[]> {
  const { data } = await api.get('/roles');
  return data.data ?? [];
}

export async function listBranches(params?: {
  page?: number;
  per_page?: number;
  search?: string;
  is_active?: boolean;
}): Promise<ListResponse<Branch>> {
  const { data } = await api.get('/branches', { params });
  return unwrapPaginated<Branch>(data);
}

export async function listEscalationRules(params?: {
  page?: number;
  per_page?: number;
  is_active?: boolean;
}): Promise<ListResponse<EscalationRule>> {
  const { data } = await api.get('/escalations/rules', { params });
  return unwrapPaginated<EscalationRule>(data);
}

export async function listEscalationEvents(params?: {
  page?: number;
  per_page?: number;
  trigger?: string;
}): Promise<ListResponse<EscalationEvent>> {
  const { data } = await api.get('/escalations/events', { params });
  return unwrapPaginated<EscalationEvent>(data);
}
