import { api } from '@/lib/api';

export interface HierarchyLevel {
  id: string;
  name: string;
  level_order: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface OrgUnit {
  id: string;
  hierarchy_level_id: string;
  hierarchy_level: string | null;
  parent_id: string | null;
  parent_name: string | null;
  name: string;
  code: string;
  address: string | null;
  contact_email: string | null;
  contact_phone: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  hierarchy_chain?: Array<{ id: string; name: string; code: string; level: string | null }>;
}

export interface OrgRole {
  id: string;
  hierarchy_level_id: string;
  hierarchy_level: string | null;
  name: string;
  role_order: number;
  can_manage_unit: boolean;
  can_manage_subtree: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface OrgUser {
  id: string;
  email: string;
  full_name: string;
  role: string;
  org_unit_id: string | null;
  org_unit: { id: string; name: string; code: string; level: string | null } | null;
  org_role_id: string | null;
  org_role: { id: string; name: string; can_manage_unit: boolean; can_manage_subtree: boolean } | null;
  is_super_admin: boolean;
  is_active: boolean;
  /**
   * Availability, which is not the same as `is_active`. `is_active` says
   * whether the account can log in; these say whether to route new work here.
   * Both dates inclusive; `on_leave` is the server's answer for today.
   */
  leave_from: string | null;
  leave_to: string | null;
  leave_note: string | null;
  on_leave: boolean;
  mfa_enabled: boolean;
  last_login_at: string | null;
  created_at: string;
  updated_at: string;
}

// ── Hierarchy Levels ──────────────────────────────────────────────────────────

export async function getLevels(): Promise<HierarchyLevel[]> {
  const res = await api.get('/org/levels');
  return res.data.data;
}

export async function createLevel(payload: { name: string; level_order: number }): Promise<HierarchyLevel> {
  const res = await api.post('/org/levels', payload);
  return res.data.data;
}

export async function updateLevel(id: string, payload: Partial<HierarchyLevel>): Promise<HierarchyLevel> {
  const res = await api.patch(`/org/levels/${id}`, payload);
  return res.data.data;
}

export async function deleteLevel(id: string): Promise<void> {
  await api.delete(`/org/levels/${id}`);
}

// ── Org Units ─────────────────────────────────────────────────────────────────

export interface ListUnitsParams {
  hierarchy_level_id?: string;
  parent_id?: string;
  search?: string;
  page?: number;
  per_page?: number;
}

export async function listOrgUnits(params: ListUnitsParams = {}): Promise<{ data: OrgUnit[]; total: number }> {
  const res = await api.get('/org/units', { params });
  return { data: res.data.data, total: res.data.meta?.total ?? res.data.data.length };
}

export async function getOrgUnit(id: string): Promise<OrgUnit> {
  const res = await api.get(`/org/units/${id}`);
  return res.data.data;
}

export async function createOrgUnit(payload: Partial<OrgUnit>): Promise<OrgUnit> {
  const res = await api.post('/org/units', payload);
  return res.data.data;
}

export async function updateOrgUnit(id: string, payload: Partial<OrgUnit>): Promise<OrgUnit> {
  const res = await api.patch(`/org/units/${id}`, payload);
  return res.data.data;
}

export async function deleteOrgUnit(id: string): Promise<void> {
  await api.delete(`/org/units/${id}`);
}

// ── Org Roles ─────────────────────────────────────────────────────────────────

export async function listOrgRoles(hierarchy_level_id?: string): Promise<OrgRole[]> {
  const res = await api.get('/org/roles', { params: hierarchy_level_id ? { hierarchy_level_id } : {} });
  return res.data.data;
}

export async function createOrgRole(payload: Partial<OrgRole>): Promise<OrgRole> {
  const res = await api.post('/org/roles', payload);
  return res.data.data;
}

export async function updateOrgRole(id: string, payload: Partial<OrgRole>): Promise<OrgRole> {
  const res = await api.patch(`/org/roles/${id}`, payload);
  return res.data.data;
}

export async function deleteOrgRole(id: string): Promise<void> {
  await api.delete(`/org/roles/${id}`);
}

// ── Users ─────────────────────────────────────────────────────────────────────

export interface ListUsersParams {
  org_unit_id?: string;
  role?: string;
  search?: string;
  is_active?: boolean;
  page?: number;
  per_page?: number;
}

export async function listUsers(params: ListUsersParams = {}): Promise<{ data: OrgUser[]; total: number }> {
  const res = await api.get('/users', { params });
  return { data: res.data.data, total: res.data.meta?.total ?? res.data.data.length };
}

export async function getUser(id: string): Promise<OrgUser> {
  const res = await api.get(`/users/${id}`);
  return res.data.data;
}

export async function createUser(payload: {
  email: string;
  full_name: string;
  password: string;
  role: string;
  org_unit_id?: string;
  org_role_id?: string;
  is_super_admin?: boolean;
}): Promise<OrgUser> {
  const res = await api.post('/users', payload);
  return res.data.data;
}

export async function updateUser(id: string, payload: Partial<{
  full_name: string;
  role: string;
  org_unit_id: string | null;
  org_role_id: string | null;
  is_active: boolean;
  is_super_admin: boolean;
  password: string;
}>): Promise<OrgUser> {
  const res = await api.patch(`/users/${id}`, payload);
  return res.data.data;
}

export async function deactivateUser(id: string): Promise<void> {
  await api.delete(`/users/${id}`);
}

/**
 * Record or clear a leave window. Supervisor and above.
 *
 * Pass nulls for both dates to mark somebody available again. This never
 * touches `is_active` — deactivating an account to cover leave would lock the
 * person out of the system.
 */
export async function setUserLeave(
  id: string,
  payload: { leave_from: string | null; leave_to: string | null; leave_note?: string | null },
): Promise<OrgUser> {
  const res = await api.patch(`/users/${id}/leave`, payload);
  return res.data.data;
}
