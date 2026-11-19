import { Suspense, lazy } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';

import { AppLayout } from '@/app/AppLayout';
import { RequireAuth } from '@/app/RequireAuth';
// Login and Dashboard stay in the entry chunk: one is the first thing an
// unauthenticated visitor sees, the other the first thing everyone else sees,
// so lazy-loading either would only add a spinner to the critical path.
import { DashboardPage } from '@/pages/DashboardPage';
import { LoginPage } from '@/pages/LoginPage';
import { ForbiddenPage } from '@/pages/ForbiddenPage';
import { PlaceholderPage } from '@/pages/PlaceholderPage';

// Everything else is split. Reports in particular drags in Recharts, which is
// the single largest dependency and is useless to an agent who never opens it.
const TicketsPage       = lazy(() => import('@/pages/TicketsPage').then(m => ({ default: m.TicketsPage })));
const TicketDetailPage  = lazy(() => import('@/pages/TicketDetailPage').then(m => ({ default: m.TicketDetailPage })));
const CreateTicketPage  = lazy(() => import('@/pages/CreateTicketPage').then(m => ({ default: m.CreateTicketPage })));
const AuditPage         = lazy(() => import('@/pages/AuditPage').then(m => ({ default: m.AuditPage })));
const OrgManagementPage = lazy(() => import('@/pages/OrgManagementPage').then(m => ({ default: m.OrgManagementPage })));
const UsersPage         = lazy(() => import('@/pages/UsersPage').then(m => ({ default: m.UsersPage })));
const ReportsPage       = lazy(() => import('@/pages/ReportsPage').then(m => ({ default: m.ReportsPage })));
const BranchesPage      = lazy(() => import('@/pages/BranchesPage').then(m => ({ default: m.BranchesPage })));
const SecurityPage      = lazy(() => import('@/pages/SecurityPage').then(m => ({ default: m.SecurityPage })));
const SLAMonitorPage    = lazy(() => import('@/pages/SLAMonitorPage').then(m => ({ default: m.SLAMonitorPage })));
const EscalationsPage   = lazy(() => import('@/pages/EscalationsPage').then(m => ({ default: m.EscalationsPage })));
const KnowledgeBasePage = lazy(() => import('@/pages/KnowledgeBasePage').then(m => ({ default: m.KnowledgeBasePage })));

/** Shown while a route chunk loads. Deliberately quiet — a full-page spinner
 *  for a sub-second fetch reads as slower than a blank moment. */
function RouteFallback() {
  return (
    <div className="p-6">
      <div className="animate-pulse h-6 w-40 rounded bg-[var(--inset)]" />
    </div>
  );
}

export default function App() {
  return (
    <Suspense fallback={<RouteFallback />}>
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route
        element={
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        }
      >
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard"      element={<DashboardPage />} />
        <Route path="/tickets"        element={<TicketsPage />} />
        <Route path="/tickets/new"    element={<CreateTicketPage />} />
        <Route path="/tickets/:id"    element={<TicketDetailPage />} />
        <Route
          path="/sla"
          element={
            <RequireAuth roles={['admin', 'supervisor']}>
              <SLAMonitorPage />
            </RequireAuth>
          }
        />
        <Route
          path="/escalations"
          element={
            <RequireAuth roles={['admin', 'supervisor']}>
              <EscalationsPage />
            </RequireAuth>
          }
        />
        <Route
          path="/knowledge"
          element={
            <RequireAuth roles={['admin', 'supervisor', 'agent']}>
              <KnowledgeBasePage />
            </RequireAuth>
          }
        />
        <Route
          path="/branches"
          element={
            <RequireAuth roles={['admin', 'supervisor']}>
              <BranchesPage />
            </RequireAuth>
          }
        />
        <Route
          path="/users"
          element={
            <RequireAuth roles={['admin', 'supervisor']}>
              <UsersPage />
            </RequireAuth>
          }
        />
        <Route
          path="/org"
          element={
            <RequireAuth roles={['admin']}>
              <OrgManagementPage />
            </RequireAuth>
          }
        />
        <Route
          path="/reports"
          element={
            <RequireAuth roles={['admin', 'supervisor', 'auditor']}>
              <ReportsPage />
            </RequireAuth>
          }
        />
        <Route
          path="/audit"
          element={
            <RequireAuth roles={['admin', 'auditor']}>
              <AuditPage />
            </RequireAuth>
          }
        />
        {/* Personal account security — available to every signed-in role. */}
        <Route path="/security" element={<SecurityPage />} />
        <Route path="/forbidden" element={<ForbiddenPage />} />
      </Route>

      <Route path="*" element={<PlaceholderPage title="Not found" phase="—" description="The page you requested does not exist." />} />
    </Routes>
    </Suspense>
  );
}
