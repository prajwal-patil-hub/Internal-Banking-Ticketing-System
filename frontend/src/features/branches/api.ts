import { api } from '@/lib/api';

export type BranchStatus = 'operational' | 'maintenance' | 'incident';

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
  status: BranchStatus;
  status_note: string;
  manager_id: string | null;
  manager: { id: string; full_name: string } | null;
  ticket_capacity: number;
  /** Open tickets right now — computed, never stored. */
  open_tickets: number;
  breached_tickets: number;
  /** Open tickets as a share of capacity, capped at 100 for display. */
  load_percent: number;
  created_at: string;
}

export interface BranchSummary {
  total: number;
  operational: number;
  maintenance: number;
  incident: number;
  uptime_percent: number;
  regions: string[];
}

export interface BranchFilters {
  region?: string;
  status?: BranchStatus;
  search?: string;
}

export async function listBranches(filters: BranchFilters = {}): Promise<Branch[]> {
  const params: Record<string, string> = {};
  for (const [k, v] of Object.entries(filters)) if (v) params[k] = v;
  const { data } = await api.get('/branches', { params });
  return data.data;
}

export async function getBranchSummary(): Promise<BranchSummary> {
  const { data } = await api.get('/branches/summary');
  return data.data;
}

export async function createBranch(payload: Partial<Branch>): Promise<Branch> {
  const { data } = await api.post('/branches', payload);
  return data.data;
}

export async function updateBranch(id: string, payload: Partial<Branch>): Promise<Branch> {
  const { data } = await api.patch(`/branches/${id}`, payload);
  return data.data;
}

/** CSV of the whole network, including the derived load figures. */
export async function exportBranchesCsv(): Promise<void> {
  const res = await api.get('/branches/export', { responseType: 'blob' });
  const url = URL.createObjectURL(new Blob([res.data], { type: 'text/csv' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = `branches_${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
