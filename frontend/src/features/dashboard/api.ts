import { api } from '@/lib/api';

export interface DashboardKpis {
  open: number;
  breached: number;
  response_breached: number;
  critical_open: number;
  resolved: number;
  open_escalations: number;
  sla_health: number;
  role: string;
}

export interface DashboardRecent {
  id: string;
  ticket_no: string;
  title: string;
  status: string;
  priority: string;
  sla_due_at: string | null;
  created_at: string;
}

export interface DashboardOverview {
  kpis: DashboardKpis;
  recent: DashboardRecent[];
  role_specific: Record<string, number>;
}

export async function dashboardOverview(): Promise<DashboardOverview> {
  const { data } = await api.get<{ data: DashboardOverview }>('/dashboard/overview');
  return data.data;
}

export interface DashboardAnalytics {
  by_status: Record<string, number>;
  by_priority: Record<string, number>;
  by_category: { name: string; total: number; open: number }[];
  daily_volume: { date: string; total: number; critical: number }[];
  top_branches: { code: string; name: string; count: number }[];
  avg_resolution_minutes: { priority: string; minutes: number | null; n: number }[];
}

export async function dashboardAnalytics(): Promise<DashboardAnalytics> {
  const { data } = await api.get<{ data: DashboardAnalytics }>('/dashboard/analytics');
  return data.data;
}
