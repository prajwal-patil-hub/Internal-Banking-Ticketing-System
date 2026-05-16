import { api } from '@/lib/api';

export interface KPIData {
  open_tickets: number;
  sla_breached: number;
  resolved_today: number;
  avg_resolution_hours: number;
  critical_open: number;
  ai_auto_categorized: number;
  email_tickets_today: number;
  escalations_active: number;
}

export interface SLAStatus {
  on_time: number;
  at_risk: number;
  breached: number;
  compliance_rate: number;
}

export interface CategoryItem {
  category: string;
  count: number;
  percentage: number;
}

export interface DepartmentLoad {
  department: string;
  open_count: number;
  breached_count: number;
  avg_age_hours: number;
}

export interface AIMetrics {
  total_categorized: number;
  avg_confidence: number;
  high_risk_tickets: number;
  auto_resolved: number;
  avg_latency_ms: number;
}

export async function getDashboardKPIs(): Promise<KPIData> {
  const { data } = await api.get('/dashboard/kpis');
  const k = data.data ?? {};
  return {
    open_tickets: k.total_open_tickets ?? 0,
    sla_breached: k.sla_breached_open ?? 0,
    resolved_today: k.resolved_today ?? 0,
    avg_resolution_hours: k.avg_resolution_hours_30d ?? 0,
    critical_open: k.critical_high_open ?? 0,
    ai_auto_categorized: k.ai_auto_categorized ?? 0,
    email_tickets_today: k.email_tickets_today ?? 0,
    escalations_active: k.escalations_active ?? 0,
  };
}

export async function getSLAStatus(): Promise<SLAStatus> {
  const { data } = await api.get('/dashboard/sla-status');
  const s = data.data ?? {};
  const total = s.total_tracked ?? 0;
  const breached = s.resolution_sla_breached ?? 0;
  const at_risk = s.at_risk_next_60min ?? 0;
  const on_time = Math.max(total - breached - at_risk, 0);
  return {
    on_time,
    at_risk,
    breached,
    compliance_rate: s.sla_compliance_rate ?? 100,
  };
}

export async function getCategoryDistribution(): Promise<CategoryItem[]> {
  const { data } = await api.get('/dashboard/category-distribution');
  const payload = data.data ?? {};
  const total = payload.total_tickets ?? 0;
  const distribution: Array<{ category_name: string; ticket_count: number }> = payload.distribution ?? [];
  return distribution.map((d) => ({
    category: d.category_name,
    count: d.ticket_count ?? 0,
    percentage: total > 0 ? ((d.ticket_count ?? 0) / total) * 100 : 0,
  }));
}

export async function getDepartmentLoad(): Promise<DepartmentLoad[]> {
  const { data } = await api.get('/dashboard/department-load');
  const rows: Array<{
    department: string;
    open_tickets?: number;
    sla_breached?: number;
  }> = data.data?.department_load ?? [];
  return rows.map((r) => ({
    department: r.department,
    open_count: r.open_tickets ?? 0,
    breached_count: r.sla_breached ?? 0,
    avg_age_hours: 0,
  }));
}

export async function getRecentTickets(): Promise<unknown[]> {
  const { data } = await api.get('/dashboard/recent-tickets');
  return data.data ?? [];
}

export async function getAIMetrics(): Promise<AIMetrics> {
  const { data } = await api.get('/dashboard/ai-metrics');
  const m = data.data ?? {};
  const byType = m.by_interaction_type ?? {};
  const categorize = byType.categorize ?? {};
  return {
    total_categorized: categorize.count ?? 0,
    avg_confidence: categorize.avg_confidence ?? 0,
    high_risk_tickets: 0,
    auto_resolved: 0,
    avg_latency_ms: m.avg_latency_ms ?? 0,
  };
}
