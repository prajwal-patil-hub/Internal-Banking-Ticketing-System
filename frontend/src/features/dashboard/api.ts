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

export interface DashboardData {
  kpis: KPIData;
  department_load: Array<{
    department: string;
    open_count: number;
    breached_count: number;
    avg_age_hours: number;
  }>;
  category_distribution: Array<{
    category: string;
    count: number;
    percentage: number;
  }>;
  sla_status: {
    on_time: number;
    at_risk: number;
    breached: number;
    compliance_rate: number;
  };
  recent_tickets: unknown[];
}

export interface SLAStatus {
  on_time: number;
  at_risk: number;
  breached: number;
  compliance_rate: number;
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
  return data.data;
}

export async function getSLAStatus(): Promise<SLAStatus> {
  const { data } = await api.get('/dashboard/sla');
  return data.data;
}

export async function getCategoryDistribution(): Promise<Array<{ category: string; count: number; percentage: number }>> {
  const { data } = await api.get('/dashboard/categories');
  return data.data;
}

export async function getDepartmentLoad(): Promise<Array<{
  department: string;
  open_count: number;
  breached_count: number;
  avg_age_hours: number;
}>> {
  const { data } = await api.get('/dashboard/departments');
  return data.data;
}

export async function getRecentTickets(): Promise<unknown[]> {
  const { data } = await api.get('/dashboard/recent-tickets');
  return data.data;
}

export async function getAIMetrics(): Promise<AIMetrics> {
  const { data } = await api.get('/dashboard/ai-metrics');
  return data.data;
}
