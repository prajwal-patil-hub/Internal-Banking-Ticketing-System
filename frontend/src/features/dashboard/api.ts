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
