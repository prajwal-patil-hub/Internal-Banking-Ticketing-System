import { Navigate, Route, Routes } from 'react-router-dom';

import { AppLayout } from '@/app/AppLayout';
import { DashboardPage } from '@/pages/DashboardPage';
import { LoginPage } from '@/pages/LoginPage';
import { PlaceholderPage } from '@/pages/PlaceholderPage';

/**
 * Top-level route map.
 *
 * Phase P0 wires: /login (shell only), and an unauthenticated AppLayout so the
 * design language is verifiable end-to-end. Phase P1 introduces an auth guard
 * that redirects unauthenticated users to /login.
 */
export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route element={<AppLayout />}>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard"   element={<DashboardPage />} />
        <Route path="/tickets"     element={<PlaceholderPage title="Tickets" phase="P2" />} />
        <Route path="/sla"         element={<PlaceholderPage title="SLA Monitor" phase="P4 / P7" />} />
        <Route path="/escalations" element={<PlaceholderPage title="Escalations" phase="P5" />} />
        <Route path="/branches"    element={<PlaceholderPage title="Branches" phase="P2" />} />
        <Route path="/users"       element={<PlaceholderPage title="Users & Roles" phase="P1" />} />
        <Route path="/audit"       element={<PlaceholderPage title="Audit Log" phase="P6" />} />
      </Route>

      <Route path="*" element={<PlaceholderPage title="Not found" phase="—" description="The page you requested does not exist." />} />
    </Routes>
  );
}
