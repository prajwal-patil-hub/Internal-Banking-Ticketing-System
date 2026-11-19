import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/Button';
import { cn } from '@/lib/cn';
import { extractError } from '@/lib/api';
import { useAuth } from '@/store/auth';
import { PageHeader, PageShell } from '@/components/PageHeader';
import {
  listBranches,
  getBranchSummary,
  exportBranchesCsv,
  type Branch,
  type BranchStatus,
} from '@/features/branches/api';

/**
 * The branch network: which branches are up, who runs them, how loaded.
 *
 * `/branches` used to redirect to the org hierarchy, which answers a different
 * question — org units are the reporting tree, branches are physical places
 * with staff and a service state.
 */

const STATUS_META: Record<BranchStatus, { label: string; dot: string; pill: string }> = {
  operational: { label: 'Operational', dot: 'bg-[var(--ok)]',   pill: 'pill-ok' },
  maintenance: { label: 'Maintenance', dot: 'bg-[var(--warn)]', pill: 'pill-warn' },
  incident:    { label: 'Incident',    dot: 'bg-[var(--err)]',  pill: 'pill-err' },
};

function Sk({ className }: { className?: string }) {
  return <div className={cn('animate-pulse rounded-lg bg-[var(--inset)]', className)} />;
}

function StatTile({ label, value, sub, tone = 'default' }: {
  label: string; value: string | number; sub?: string;
  tone?: 'default' | 'ok' | 'warn' | 'err';
}) {
  const valueTone = {
    default: 'text-[var(--tx)]', ok: 'text-[var(--ok)]',
    warn: 'text-[var(--warn)]',  err: 'text-[var(--err)]',
  }[tone];
  return (
    <div className="card-sm flex flex-col gap-1">
      <span className="text-[11px] uppercase tracking-widest text-[var(--tx-3)] font-semibold">
        {label}
      </span>
      <span className={cn('text-2xl font-bold tabular-nums leading-none', valueTone)}>
        {value}
      </span>
      {sub && <span className="text-[11px] text-[var(--tx-3)]">{sub}</span>}
    </div>
  );
}

/** The network strip: one dot per branch, coloured by service state. */
function NetworkStrip({ branches, onSelect }: {
  branches: Branch[];
  onSelect: (code: string) => void;
}) {
  return (
    <div className="card-sm flex flex-col gap-3">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <h2 className="text-sm font-semibold text-[var(--tx)]">Branch Network</h2>
        <div className="flex items-center gap-3 text-[11px] text-[var(--tx-3)]">
          {(Object.keys(STATUS_META) as BranchStatus[]).map((s) => (
            <span key={s} className="flex items-center gap-1.5">
              <span className={cn('h-2 w-2 rounded-full', STATUS_META[s].dot)} />
              {STATUS_META[s].label}
            </span>
          ))}
        </div>
      </div>

      <div className="flex flex-wrap gap-x-5 gap-y-4 justify-center py-3">
        {branches.map((b) => (
          <button
            key={b.id}
            type="button"
            onClick={() => onSelect(b.code)}
            title={b.status_note || `${b.name} — ${STATUS_META[b.status].label}`}
            className="flex flex-col items-center gap-1.5 group focus-visible:outline-none"
          >
            <span
              className={cn(
                'h-11 w-11 rounded-full flex items-center justify-center',
                'text-[11px] font-bold text-white tracking-wide',
                'transition-transform duration-150 group-hover:scale-110',
                'group-focus-visible:ring-2 group-focus-visible:ring-[var(--brand)]',
                'group-focus-visible:ring-offset-2 group-focus-visible:ring-offset-[var(--bg)]',
                STATUS_META[b.status].dot,
              )}
            >
              {b.code.split('-')[0]}
            </span>
            <span className="text-[10px] text-[var(--tx-3)] max-w-[70px] truncate">
              {b.name}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}

function LoadBar({ percent, breached }: { percent: number; breached: number }) {
  // Colour by pressure, not by brand: a branch at 90% needs to look different
  // from one at 20% without the reader comparing numbers.
  const tone =
    percent >= 80 ? 'bg-[var(--err)]' : percent >= 50 ? 'bg-[var(--warn)]' : 'bg-[var(--ok)]';
  return (
    <div className="flex items-center gap-2 min-w-[110px]">
      <div className="flex-1 h-1.5 rounded-full bg-[var(--inset)] overflow-hidden">
        <div className={cn('h-full rounded-full transition-all duration-500', tone)}
             style={{ width: `${percent}%` }} />
      </div>
      <span className="text-[11px] tabular-nums text-[var(--tx-3)] w-9 text-right">
        {percent}%
      </span>
      {breached > 0 && (
        <span className="pill pill-err text-[10px]" title={`${breached} breached`}>
          {breached}
        </span>
      )}
    </div>
  );
}

export function BranchesPage() {
  const navigate = useNavigate();
  const role = useAuth((s) => s.user?.role);
  const canExport = role === 'admin' || role === 'supervisor';

  const [search, setSearch] = useState('');
  const [region, setRegion] = useState('');
  const [statusFilter, setStatusFilter] = useState<BranchStatus | ''>('');
  const [exportError, setExportError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

  const { data: summary } = useQuery({
    queryKey: ['branch-summary'],
    queryFn: getBranchSummary,
  });

  const { data: branches = [], isLoading } = useQuery({
    queryKey: ['branches', region, statusFilter, search],
    queryFn: () => listBranches({
      ...(region ? { region } : {}),
      ...(statusFilter ? { status: statusFilter } : {}),
      ...(search ? { search } : {}),
    }),
  });

  const handleExport = async () => {
    setExporting(true);
    setExportError(null);
    try {
      await exportBranchesCsv();
    } catch (e) {
      setExportError(extractError(e).message);
    } finally {
      setExporting(false);
    }
  };

  return (
    <PageShell>
      <PageHeader
        title="Branch Management"
        subtitle={summary ? `${summary.total} branches · ${summary.regions.length} regions` : 'Loading…'}
        actions={canExport && (
          <Button variant="ghost" onClick={handleExport} disabled={exporting}>
            {exporting ? 'Preparing…' : 'Export CSV'}
          </Button>
        )}
      />
      {exportError && <p className="text-xs text-[var(--err)] -mt-3">{exportError}</p>}

      {/* Network health */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {summary ? (
          <>
            <StatTile label="Total Branches" value={summary.total} />
            <StatTile label="Operational" value={summary.operational} tone="ok"
                      sub={`${summary.uptime_percent}% of the network`} />
            <StatTile label="Under Maintenance" value={summary.maintenance} tone="warn"
                      sub="Scheduled" />
            <StatTile label="Incident Active" value={summary.incident} tone="err"
                      sub={summary.incident > 0 ? 'Needs attention' : 'All clear'} />
          </>
        ) : (
          [0, 1, 2, 3].map((i) => <div key={i} className="card-sm"><Sk className="h-14" /></div>)
        )}
      </div>

      {!isLoading && branches.length > 0 && (
        <NetworkStrip branches={branches} onSelect={setSearch} />
      )}

      {/* Filters */}
      <div className="flex items-center gap-2 flex-wrap">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search branches…"
          aria-label="Search branches"
          className="flex-1 min-w-[180px] rounded-lg border border-[var(--line)] bg-[var(--bg)] px-3 py-2 text-sm text-[var(--tx)] outline-none focus:border-[var(--brand)]"
        />
        <select
          value={region}
          onChange={(e) => setRegion(e.target.value)}
          aria-label="Filter by region"
          className="rounded-lg border border-[var(--line)] bg-[var(--bg)] px-3 py-2 text-sm text-[var(--tx)] outline-none focus:border-[var(--brand)]"
        >
          <option value="">All Regions</option>
          {(summary?.regions ?? []).map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as BranchStatus | '')}
          aria-label="Filter by status"
          className="rounded-lg border border-[var(--line)] bg-[var(--bg)] px-3 py-2 text-sm text-[var(--tx)] outline-none focus:border-[var(--brand)]"
        >
          <option value="">All Status</option>
          {(Object.keys(STATUS_META) as BranchStatus[]).map((s) => (
            <option key={s} value={s}>{STATUS_META[s].label}</option>
          ))}
        </select>
        {(search || region || statusFilter) && (
          <button
            onClick={() => { setSearch(''); setRegion(''); setStatusFilter(''); }}
            className="text-xs text-[var(--tx-3)] hover:text-[var(--tx)] transition-colors"
          >
            Clear
          </button>
        )}
        <span className="text-xs text-[var(--tx-3)] ml-auto">
          {branches.length} {branches.length === 1 ? 'branch' : 'branches'}
        </span>
      </div>

      {/* Table */}
      <div className="card-sm !p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm min-w-[820px]">
            <thead>
              <tr className="border-b border-[var(--line)]">
                {['Branch', 'Code', 'Region', 'Manager', 'Tickets Open', 'Load', 'Status'].map((h) => (
                  <th key={h} className="text-left px-4 py-2.5 text-[11px] uppercase tracking-widest text-[var(--tx-3)] font-semibold whitespace-nowrap">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                [0, 1, 2, 3, 4].map((i) => (
                  <tr key={i} className="border-b border-[var(--line)] last:border-0">
                    <td colSpan={7} className="px-4 py-3"><Sk className="h-4" /></td>
                  </tr>
                ))
              ) : branches.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-10 text-center text-sm text-[var(--tx-3)]">
                    No branches match these filters.
                  </td>
                </tr>
              ) : (
                branches.map((b) => (
                  <tr key={b.id} className="border-b border-[var(--line)] last:border-0 hover:bg-[var(--inset)] transition-colors">
                    <td className="px-4 py-3 font-medium text-[var(--tx)]">{b.name}</td>
                    <td className="px-4 py-3 font-mono text-xs text-[var(--tx-3)]">{b.code}</td>
                    <td className="px-4 py-3 text-[var(--tx-2)]">{b.region || '—'}</td>
                    <td className="px-4 py-3 text-[var(--tx-2)]">
                      {b.manager?.full_name ?? '—'}
                    </td>
                    <td className="px-4 py-3">
                      {/* Straight to this branch's open queue. */}
                      <button
                        onClick={() => navigate(`/tickets?status_group=open&q=${encodeURIComponent(b.code)}`)}
                        className="pill pill-neu tabular-nums hover:opacity-80 transition-opacity"
                        title={`View open tickets at ${b.name}`}
                      >
                        {b.open_tickets}
                      </button>
                    </td>
                    <td className="px-4 py-3">
                      <LoadBar percent={b.load_percent} breached={b.breached_tickets} />
                    </td>
                    <td className="px-4 py-3">
                      <span className={cn('pill', STATUS_META[b.status].pill)}>
                        <span className={cn('h-1.5 w-1.5 rounded-full mr-1', STATUS_META[b.status].dot)} />
                        {STATUS_META[b.status].label}
                      </span>
                      {b.status_note && (
                        <p className="text-[10px] text-[var(--tx-3)] mt-1 max-w-[180px]">
                          {b.status_note}
                        </p>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </PageShell>
  );
}
