import { Card } from '@/components/Card';
import { Link } from 'react-router-dom';

export function ForbiddenPage() {
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold tracking-tight">403 — Forbidden</h1>
      <Card>
        <p className="text-sm text-slate-600 dark:text-slate-300">
          Your role does not grant access to this resource. Please contact your
          administrator if you believe this is a mistake.
        </p>
        <Link to="/dashboard" className="btn-primary mt-4 inline-flex">Back to dashboard</Link>
      </Card>
    </div>
  );
}
