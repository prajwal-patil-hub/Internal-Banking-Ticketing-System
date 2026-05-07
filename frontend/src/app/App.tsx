import { Navigate, Route, Routes } from 'react-router-dom';

import { AppLayout } from '@/app/AppLayout';
import { RequireAuth } from '@/app/RequireAuth';
import { DashboardPage } from '@/pages/DashboardPage';
import { LoginPage } from '@/pages/LoginPage';
import { ForbiddenPage } from '@/pages/ForbiddenPage';
import { PlaceholderPage } from '@/pages/PlaceholderPage';
import { TicketsPage } from '@/pages/TicketsPage';
import { TicketDetailPage } from '@/pages/TicketDetailPage';
import { BranchesPage } from '@/pages/BranchesPage';
import { UsersPage } from '@/pages/UsersPage';
import { SlaPage } from '@/pages/SlaPage';
import { EscalationsPage } from '@/pages/EscalationsPage';
import { AuditPage } from '@/pages/AuditPage';
import { ProfilePage } from '@/pages/ProfilePage';

export default function App() {
  return (
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
        <Route path="/dashboard"        element={<DashboardPage />} />
        <Route path="/tickets"          element={<TicketsPage />} />
        <Route path="/tickets/:id"      element={<TicketDetailPage />} />
        <Route
          path="/sla"
          element={
            <RequireAuth roles={['admin', 'supervisor']}>
              <SlaPage />
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
          path="/branches"
          element={
            <RequireAuth roles={['admin']}>
              <BranchesPage />
            </RequireAuth>
          }
        />
        <Route
          path="/users"
          element={
            <RequireAuth roles={['admin']}>
              <UsersPage />
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
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/forbidden" element={<ForbiddenPage />} />
      </Route>

      <Route
        path="*"
        element={
          <PlaceholderPage
            title="Not found"
            phase="—"
            description="The page you requested does not exist."
          />
        }
      />
    </Routes>
  );
}
