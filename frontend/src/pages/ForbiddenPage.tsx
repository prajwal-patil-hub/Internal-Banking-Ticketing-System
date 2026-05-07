import { Link } from 'react-router-dom';
import { Lock } from 'lucide-react';

import { Card } from '@/components/Card';

export function ForbiddenPage() {
  return (
    <div className="flex flex-col gap-4 max-w-xl mx-auto py-12">
      <Card>
        <div className="flex items-start gap-4">
          <span className="h-12 w-12 rounded-3xl grid place-items-center bg-warning-soft">
            <Lock className="h-6 w-6 text-warning-deep" />
          </span>
          <div className="min-w-0">
            <span className="label">Forbidden</span>
            <h1 className="text-2xl font-semibold tracking-tight text-ink mt-1">403 — Access denied</h1>
            <p className="text-sm text-ink-muted mt-2">
              Your role does not grant access to this resource. If you believe this is a
              mistake, please reach out to your administrator.
            </p>
            <Link to="/dashboard" className="btn-primary mt-5 inline-flex">Back to dashboard</Link>
          </div>
        </div>
      </Card>
    </div>
  );
}
