import { describe, expect, it } from 'vitest';

import type { AuthUser, Role } from '@/store/auth';
import {
  canManageKnowledgeBase,
  canManageOrg,
  canManageUsers,
  canQueryKnowledgeBase,
  canRaiseTicket,
  canSeeOrgMetrics,
  canViewAudit,
  canViewBranches,
  canViewEscalations,
  canViewReports,
  canViewSLA,
  canWriteTickets,
  isReadOnly,
} from '@/lib/permissions';

const ROLES: Role[] = ['branch_user', 'agent', 'supervisor', 'admin', 'auditor'];

function userWith(role: Role, superAdmin = false): AuthUser {
  return {
    id: 'u1',
    email: `${role}@success.test`,
    full_name: 'Test User',
    role,
    branch_id: null,
    mfa_enabled: false,
    org_unit_id: null,
    org_unit: null,
    org_role_id: null,
    org_role: null,
    is_super_admin: superAdmin,
  };
}

/**
 * The expected matrix, written out per role rather than derived from the code
 * under test — a table generated from the implementation would agree with any
 * implementation, including a wrong one.
 *
 * This must match `backend/app/core/authz.py` and the `RequireAuth` guards in
 * `app/App.tsx`. When a rule changes there, change it here in the same commit
 * and let this test prove the UI followed.
 */
const MATRIX: Record<Role, Record<string, boolean>> = {
  branch_user: {
    raiseTicket: true,  writeTickets: false, viewSLA: false, viewEscalations: false,
    viewBranches: false, viewReports: false, viewAudit: false, manageUsers: false,
    manageOrg: false, queryKB: false, manageKB: false, orgMetrics: false, readOnly: false,
  },
  agent: {
    raiseTicket: true,  writeTickets: true,  viewSLA: false, viewEscalations: false,
    viewBranches: false, viewReports: false, viewAudit: false, manageUsers: false,
    manageOrg: false, queryKB: true,  manageKB: false, orgMetrics: true,  readOnly: false,
  },
  supervisor: {
    raiseTicket: true,  writeTickets: true,  viewSLA: true,  viewEscalations: true,
    viewBranches: true,  viewReports: true,  viewAudit: false, manageUsers: true,
    manageOrg: false, queryKB: true,  manageKB: false, orgMetrics: true,  readOnly: false,
  },
  admin: {
    raiseTicket: true,  writeTickets: true,  viewSLA: true,  viewEscalations: true,
    viewBranches: true,  viewReports: true,  viewAudit: true,  manageUsers: true,
    manageOrg: true,  queryKB: true,  manageKB: true,  orgMetrics: true,  readOnly: false,
  },
  auditor: {
    raiseTicket: false, writeTickets: false, viewSLA: false, viewEscalations: false,
    viewBranches: false, viewReports: true,  viewAudit: true,  manageUsers: false,
    manageOrg: false, queryKB: false, manageKB: false, orgMetrics: true,  readOnly: true,
  },
};

const GATES: Record<string, (u: AuthUser) => boolean> = {
  raiseTicket: canRaiseTicket,
  writeTickets: canWriteTickets,
  viewSLA: canViewSLA,
  viewEscalations: canViewEscalations,
  viewBranches: canViewBranches,
  viewReports: canViewReports,
  viewAudit: canViewAudit,
  manageUsers: canManageUsers,
  manageOrg: canManageOrg,
  queryKB: canQueryKnowledgeBase,
  manageKB: canManageKnowledgeBase,
  orgMetrics: canSeeOrgMetrics,
  readOnly: isReadOnly,
};

describe('permission matrix', () => {
  for (const role of ROLES) {
    for (const [gate, expected] of Object.entries(MATRIX[role])) {
      it(`${role} · ${gate} === ${expected}`, () => {
        expect(GATES[gate](userWith(role))).toBe(expected);
      });
    }
  }
});

describe('the super-admin flag widens, it does not convert', () => {
  // The backend learned this the hard way: a branch_user carrying the flag
  // fell through `user.is_super_admin || ...` and gained knowledge-base
  // curation plus a view of every collection in the bank. See KB_NEVER_ROLES.
  it('does not give a branch user knowledge-base access', () => {
    const u = userWith('branch_user', true);
    expect(canQueryKnowledgeBase(u)).toBe(false);
    expect(canManageKnowledgeBase(u)).toBe(false);
  });

  it('does not give an auditor write access', () => {
    const u = userWith('auditor', true);
    expect(canWriteTickets(u)).toBe(false);
    expect(canRaiseTicket(u)).toBe(false);
    expect(canQueryKnowledgeBase(u)).toBe(false);
  });

  it('does widen an agent into ticket writes and the knowledge base', () => {
    const u = userWith('agent', true);
    expect(canWriteTickets(u)).toBe(true);
    expect(canQueryKnowledgeBase(u)).toBe(true);
  });
});

describe('null user', () => {
  it('is granted nothing', () => {
    for (const [name, gate] of Object.entries(GATES)) {
      // `isReadOnly(null)` is false, which is correct — a signed-out visitor is
      // not a read-only *role*. Every affirmative gate must refuse.
      if (name === 'readOnly') continue;
      expect(gate(null as unknown as AuthUser)).toBe(false);
    }
  });
});
