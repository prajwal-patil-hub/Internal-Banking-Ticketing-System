import { Navigate, Route, Routes } from 'react-router-dom';

import { AppLayout } from '@/app/AppLayout';
import { RequireAuth } from '@/app/RequireAuth';
import { DashboardPage } from '@/pages/DashboardPage';
import { LoginPage } from '@/pages/LoginPage';
import { ForbiddenPage } from '@/pages/ForbiddenPage';
import { PlaceholderPage } from '@/pages/PlaceholderPage';

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
        <Route path="/dashboard"   element={<DashboardPage />} />
        <Route path="/tickets"     element={<PlaceholderPage title="Tickets"      phase="P2" />} />
        <Route
          path="/sla"
          element={
            <RequireAuth roles={['admin', 'supervisor']}>
              <PlaceholderPage title="SLA Monitor" phase="P4 / P7" />
            </RequireAuth>
          }
        />
        <Route
          path="/escalations"
          element={
            <RequireAuth roles={['admin', 'supervisor']}>
              <PlaceholderPage title="Escalations" phase="P5" />
            </RequireAuth>
          }
        />
        <Route
          path="/branches"
          element={
            <RequireAuth roles={['admin']}>
              <PlaceholderPage title="Branches" phase="P2" />
            </RequireAuth>
          }
        />
        <Route
          path="/users"
          element={
            <RequireAuth roles={['admin']}>
              <PlaceholderPage title="Users & Roles" phase="P1+" />
            </RequireAuth>
          }
        />
        <Route
          path="/audit"
          element={
            <RequireAuth roles={['admin', 'auditor']}>
              <PlaceholderPage title="Audit Log" phase="P6" />
            </RequireAuth>
          }
        />
        <Route path="/forbidden" element={<ForbiddenPage />} />
      </Route>

      <Route path="*" element={<PlaceholderPage title="Not found" phase="—" description="The page you requested does not exist." />} />
    </Routes>
  );
}
