import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import { Card } from '@/components/Card';
import { Button } from '@/components/Button';
import {
  listEscalationEvents,
  listEscalationRules,
} from '@/features/admin/api';
import type { EscalationEvent, EscalationRule } from '@/features/admin/api';
import { cn } from '@/lib/cn';

const STALE = 30_000;

function fmt(d: string | null) {
  if (!d) return '—';
  return new Date(d).toLocaleString();
}

function TriggerPill({ trigger }: { trigger: string }) {
  const tone: Record<string, string> = {
    sla_breach:    'bg-oxblood-50 text-oxblood',
    manual:        'bg-cream-200 text-ink-700',
    high_risk:     'bg-accent-50 text-accent-600',
    vip_customer:  'bg-brand-50 text-brand-700',
    regulatory:    'bg-accent-100 text-accent-600',
  };
  return (
    <span className={cn('pill normal-case tracking-normal', tone[trigger] ?? 'bg-cream-200 text-ink-700')}>
      {trigger.replace('_', ' ')}
    </span>
  );
}

export function EscalationsPage() {
  const [tab, setTab] = useState<'events' | 'rules'>('events');
  const [page, setPage] = useState(1);

  const events = useQuery({
    queryKey: ['escalations', 'events', page],
    queryFn: () => listEscalationEvents({ page, per_page: 25 }),
    staleTime: STALE,
    enabled: tab === 'events',
  });

  const rules = useQuery({
    queryKey: ['escalations', 'rules'],
    queryFn: () => listEscalationRules({ per_page: 100 }),
    staleTime: 60_000,
    enabled: tab === 'rules',
  });

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="font-display text-2xl tracking-tight text-ink-900 dark:text-ink-50">Escalations</h1>
        <p className="text-sm text-ink-500 mt-1">
          Tickets bumped up the chain — by SLA breach, risk score, VIP status, or manual override.
        </p>
      </header>

      <div className="flex items-center gap-1 border-b border-cream-200">
        {(['events', 'rules'] as const).map((t) => (
          <button
            key={t}
            onClick={() => { setTab(t); setPage(1); }}
            className={cn(
              'px-4 py-2 text-sm font-medium border-b-2 transition-colors',
              tab === t
                ? 'border-brand-600 text-brand-700 dark:text-cream-50'
                : 'border-transparent text-ink-500 hover:text-ink-700',
            )}
          >
            {t === 'events' ? 'Event log' : 'Rules'}
          </button>
        ))}
      </div>

      {tab === 'events' && (
        <>
          {events.isError && (
            <Card className="flex flex-col items-center gap-3 py-8">
              <p className="text-sm text-oxblood">Failed to load escalation events.</p>
              <Button variant="ghost" onClick={() => events.refetch()}>Retry</Button>
            </Card>
          )}
          <Card padded={false}>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-cream-200 text-xs uppercase tracking-wide text-ink-500">
                    <th className="text-left px-5 py-3 font-medium">Triggered</th>
                    <th className="text-left px-4 py-3 font-medium">Trigger</th>
                    <th className="text-left px-4 py-3 font-medium">Rule</th>
                    <th className="text-left px-4 py-3 font-medium">Escalated to</th>
                    <th className="text-left px-4 py-3 font-medium">By</th>
                    <th className="text-left px-4 py-3 font-medium">Resolved</th>
                  </tr>
                </thead>
                <tbody>
                  {events.isLoading ? (
                    Array.from({ length: 5 }).map((_, i) => (
                      <tr key={i} className="border-b border-cream-200/40">
                        {Array.from({ length: 6 }).map((__, j) => (
                          <td key={j} className="px-4 py-3">
                            <div className="h-4 w-full max-w-[140px] rounded bg-cream-200 animate-pulse" />
                          </td>
                        ))}
                      </tr>
                    ))
                  ) : (events.data?.items ?? []).length === 0 ? (
                    <tr>
                      <td colSpan={6} className="px-5 py-12 text-center text-ink-300 text-sm">
                        No escalation events yet — quiet ops floor.
                      </td>
                    </tr>
                  ) : (
                    (events.data?.items ?? []).map((e: EscalationEvent) => (
                      <tr key={e.id} className="border-b border-cream-200/40 hover:bg-cream-50">
                        <td className="px-5 py-3 text-xs text-ink-700">{fmt(e.triggered_at)}</td>
                        <td className="px-4 py-3"><TriggerPill trigger={e.trigger} /></td>
                        <td className="px-4 py-3 text-ink-700">{e.rule_name ?? '—'}</td>
                        <td className="px-4 py-3 text-ink-700">{e.escalated_to_email ?? '—'}</td>
                        <td className="px-4 py-3 text-ink-700">{e.escalated_by_email ?? 'system'}</td>
                        <td className="px-4 py-3 text-xs text-ink-500">{fmt(e.resolved_at)}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </Card>
          {(events.data?.total_pages ?? 1) > 1 && (
            <div className="flex items-center justify-between">
              <span className="text-xs text-ink-500">Page {page} of {events.data?.total_pages}</span>
              <div className="flex items-center gap-2">
                <Button variant="ghost" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Previous</Button>
                <Button variant="ghost" size="sm" disabled={page >= (events.data?.total_pages ?? 1)} onClick={() => setPage((p) => p + 1)}>Next</Button>
              </div>
            </div>
          )}
        </>
      )}

      {tab === 'rules' && (
        <>
          {rules.isError && (
            <Card className="flex flex-col items-center gap-3 py-8">
              <p className="text-sm text-oxblood">Failed to load rules.</p>
              <Button variant="ghost" onClick={() => rules.refetch()}>Retry</Button>
            </Card>
          )}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {rules.isLoading ? (
              Array.from({ length: 4 }).map((_, i) => (
                <Card key={i}>
                  <div className="h-4 w-40 rounded bg-cream-200 animate-pulse mb-2" />
                  <div className="h-3 w-56 rounded bg-cream-200 animate-pulse" />
                </Card>
              ))
            ) : (rules.data?.items ?? []).length === 0 ? (
              <Card className="md:col-span-2 text-center py-12">
                <p className="text-sm text-ink-300">No escalation rules defined.</p>
              </Card>
            ) : (
              (rules.data?.items ?? []).map((r: EscalationRule) => (
                <Card key={r.id} className="flex flex-col gap-2">
                  <div className="flex items-start justify-between">
                    <div>
                      <h3 className="font-medium text-ink-900 dark:text-ink-50">{r.name}</h3>
                      <p className="text-xs text-ink-500 mt-0.5 capitalize">
                        Escalates to <span className="text-ink-700">{r.escalate_to_role}</span>
                      </p>
                    </div>
                    <TriggerPill trigger={r.trigger} />
                  </div>
                  <div className="text-xs text-ink-500 flex flex-col gap-0.5 mt-1">
                    {r.trigger_after_minutes != null && (
                      <span>After {r.trigger_after_minutes} minutes</span>
                    )}
                    {r.priority_threshold && <span>Priority ≥ {r.priority_threshold}</span>}
                    {r.notify_email && <span>Notifies {r.notify_email}</span>}
                    {!r.is_active && <span className="text-oxblood">Inactive</span>}
                  </div>
                </Card>
              ))
            )}
          </div>
        </>
      )}
    </div>
  );
}
