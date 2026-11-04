/**
 * What the signed-in user may do — mirrored from `backend/app/core/authz.py`.
 *
 * **The server is authoritative.** Nothing here grants anything; every call
 * these gates hide is still checked again on the backend, and must be. This
 * module exists so the UI stops *offering* actions the server will refuse.
 *
 * That is not cosmetic. Before this existed, the dashboard showed an auditor a
 * "New Ticket" button leading to a form whose submit is rejected, and showed an
 * agent an "Escalated" card linking to `/escalations` — a route the router
 * itself bounces to /forbidden. Both are dead ends that read as broken software
 * rather than as a permission boundary.
 *
 * Keep the two files in step. When a rule changes in `authz.py`, change it here
 * in the same commit; `permissions.test.ts` pins the whole matrix so a silent
 * drift fails the build.
 */

import type { AuthUser, Role } from '@/store/auth';

export const ADMIN = 'admin' as const;
export const SUPERVISOR = 'supervisor' as const;
export const AGENT = 'agent' as const;
export const AUDITOR = 'auditor' as const;
export const BRANCH_USER = 'branch_user' as const;

/** Roles that may act on tickets. `auditor` is deliberately absent. */
const TICKET_WRITE_ROLES: readonly Role[] = [AGENT, SUPERVISOR, ADMIN];

/** Roles with no write access anywhere in the product. */
const READ_ONLY_ROLES: readonly Role[] = [AUDITOR];

const ESCALATION_VIEW_ROLES: readonly Role[] = [SUPERVISOR, ADMIN];
const SLA_VIEW_ROLES: readonly Role[] = [SUPERVISOR, ADMIN];
const BRANCH_VIEW_ROLES: readonly Role[] = [SUPERVISOR, ADMIN];
const USER_ADMIN_ROLES: readonly Role[] = [SUPERVISOR, ADMIN];
const ORG_ADMIN_ROLES: readonly Role[] = [ADMIN];
const REPORT_VIEW_ROLES: readonly Role[] = [ADMIN, SUPERVISOR, AUDITOR];
const AUDIT_VIEW_ROLES: readonly Role[] = [AUDITOR, ADMIN];
const KB_QUERY_ROLES: readonly Role[] = [AGENT, SUPERVISOR, ADMIN];
const KB_MANAGE_ROLES: readonly Role[] = [ADMIN];

/** Roles the super-admin flag must never widen into knowledge-base access. */
const KB_NEVER_ROLES: readonly Role[] = [AUDITOR, BRANCH_USER];

type U = AuthUser | null | undefined;

const has = (u: U, roles: readonly Role[]): boolean => !!u && roles.includes(u.role);

export const isReadOnly = (u: U): boolean => has(u, READ_ONLY_ROLES);
export const isBranchUser = (u: U): boolean => !!u && u.role === BRANCH_USER;

/**
 * Super-admin widens an administrative role's reach; it never converts a
 * read-only role into a writing one. Same rule as `authz.can_write_tickets`.
 */
export const canWriteTickets = (u: U): boolean =>
  !!u && !isReadOnly(u) && (u.is_super_admin || has(u, TICKET_WRITE_ROLES));

/**
 * Everyone who is not read-only may raise a ticket — including a branch user,
 * for whom raising one is the entire point of their account.
 */
export const canRaiseTicket = (u: U): boolean => !!u && !isReadOnly(u);

export const canViewEscalations = (u: U): boolean => has(u, ESCALATION_VIEW_ROLES);
export const canViewSLA = (u: U): boolean => has(u, SLA_VIEW_ROLES);
export const canViewBranches = (u: U): boolean => has(u, BRANCH_VIEW_ROLES);
export const canViewReports = (u: U): boolean => has(u, REPORT_VIEW_ROLES);
export const canViewAudit = (u: U): boolean => has(u, AUDIT_VIEW_ROLES);
export const canManageUsers = (u: U): boolean => has(u, USER_ADMIN_ROLES);
export const canManageOrg = (u: U): boolean => has(u, ORG_ADMIN_ROLES);

const kbEligible = (u: U): boolean => !!u && !isReadOnly(u) && !has(u, KB_NEVER_ROLES);

export const canQueryKnowledgeBase = (u: U): boolean =>
  kbEligible(u) && (u!.is_super_admin || has(u, KB_QUERY_ROLES));

export const canManageKnowledgeBase = (u: U): boolean =>
  kbEligible(u) && (u!.is_super_admin || has(u, KB_MANAGE_ROLES));

/**
 * Whether the org-wide analytics endpoints will answer this user.
 *
 * `dashboard.py` guards every one of them with
 * `require_roles("agent", "supervisor", "admin", "auditor")` — so a branch user
 * gets 403 from all of them, which used to render four red "failed to load"
 * cards on the landing screen of the role that uses the system most. Don't ask
 * for what this role may not have.
 */
export const canSeeOrgMetrics = (u: U): boolean => !!u && !isBranchUser(u);
