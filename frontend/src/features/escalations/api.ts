import { api } from '@/lib/api';
import type { PaginatedResponse } from '@/features/tickets/api';

export interface EscalationRule {
  id: string;
  name: string;
  trigger: string;
  trigger_after_minutes: number | null;
  escalate_to_role: string;
  escalate_to_user_id: string | null;
  escalate_to_user: { id: string; email: string; full_name: string } | null;
  notify_email: string | null;
  is_active: boolean;
  priority_threshold: string | null;
  category_id: string | null;
  category: { id: string; name: string; code: string } | null;
  created_at: string;
}

export interface EscalationEvent {
  id: string;
  ticket_id: string;
  rule_id: string | null;
  rule_name: string | null;
  trigger: string;
  triggered_at: string;
  escalated_to: { id: string; email: string; full_name: string } | null;
  escalated_by: { id: string; email: string; full_name: string } | null;
  reason: string | null;
  resolved_at: string | null;
}

export async function listEscalationRules(): Promise<EscalationRule[]> {
  const { data } = await api.get('/escalations/rules');
  return data.data;
}

export async function listEscalationEvents(params?: {
  ticket_id?: string;
  unresolved_only?: boolean;
  page?: number;
  page_size?: number;
}): Promise<PaginatedResponse<EscalationEvent>> {
  const { page_size, ...rest } = params ?? {};
  const queryParams = { ...rest, ...(page_size !== undefined ? { per_page: page_size } : {}) };
  const { data } = await api.get('/escalations/events', { params: queryParams });
  const items: EscalationEvent[] = data.data ?? [];
  const pg = data.meta?.pagination ?? {};
  return {
    items,
    total:       pg.total      ?? 0,
    page:        pg.page       ?? 1,
    page_size:   pg.size       ?? (page_size ?? 20),
    total_pages: pg.pages      ?? 1,
  };
}
