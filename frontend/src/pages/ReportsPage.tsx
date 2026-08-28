import { useState, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend, LineChart, Line,
} from 'recharts';
import { Button } from '@/components/Button';
import { cn } from '@/lib/cn';
import { downloadTicketReport, exportAnalytics, type ReportFormat, type AnalyticsFormat } from '@/features/reports/api';
import { api, extractError } from '@/lib/api';
import { PageHeader, PageShell } from '@/components/PageHeader';

// ── Chart colors ──────────────────────────────────────────────────────────────

const STATUS_COLORS: Record<string, string> = {
  new:          '#6B7280',
  acknowledged: '#3B82F6',
  assigned:     '#8B5CF6',
  in_progress:  '#F59E0B',
  on_hold:      '#9CA3AF',
  escalated:    '#EF4444',
  resolved:     '#10B981',
  closed:       '#6EE7B7',
  reopened:     '#F97316',
};

const PRIORITY_COLORS: Record<string, string> = {
  critical: '#EF4444',
  high:     '#F97316',
  medium:   '#F59E0B',
  low:      '#10B981',
};

// ── Chart download helper ─────────────────────────────────────────────────────

/**
 * Rasterise a rendered Recharts SVG to a PNG data URL.
 *
 * Resolves to null rather than rejecting when there is nothing to draw, so an
 * export can carry on and produce the data-only version of the document.
 */
function chartToPngDataUrl(ref: React.RefObject<HTMLDivElement>): Promise<string | null> {
  return new Promise((resolve) => {
    const svg = ref.current?.querySelector('svg');
    if (!svg) return resolve(null);

    const svgStr = new XMLSerializer().serializeToString(svg);
    const svgUrl = URL.createObjectURL(new Blob([svgStr], { type: 'image/svg+xml;charset=utf-8' }));

    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement('canvas');
      canvas.width = (svg.clientWidth || 600) * 2;
      canvas.height = (svg.clientHeight || 300) * 2;
      const ctx = canvas.getContext('2d')!;
      // Charts use currentColor for axes and labels, which is near-white in
      // dark mode; paint a white ground so the export is legible on paper.
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      URL.revokeObjectURL(svgUrl);
      resolve(canvas.toDataURL('image/png'));
    };
    img.onerror = () => { URL.revokeObjectURL(svgUrl); resolve(null); };
    img.src = svgUrl;
  });
}

function triggerDownload(href: string, filename: string) {
  const a = document.createElement('a');
  a.href = href;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

async function downloadChartAsPng(ref: React.RefObject<HTMLDivElement>, name: string) {
  const png = await chartToPngDataUrl(ref);
  if (png) triggerDownload(png, `${name}.png`);
}

// ── Stat cards ────────────────────────────────────────────────────────────────

function StatCard({ label, value, sub, tone = 'default' }: {
  label: string; value: string | number; sub?: string;
  tone?: 'default' | 'danger' | 'success' | 'warning';
}) {
  const colors = {
    default: { value: 'text-[var(--tx)]',   bg: 'bg-[var(--brand-xs)]',  text: 'text-[var(--brand)]' },
    danger:  { value: 'text-[var(--err)]',  bg: 'bg-[var(--err-bg)]',   text: 'text-[var(--err)]' },
    success: { value: 'text-[var(--ok)]',   bg: 'bg-[var(--ok-bg)]',    text: 'text-[var(--ok)]' },
    warning: { value: 'text-[var(--warn)]', bg: 'bg-[var(--warn-bg)]',  text: 'text-[var(--warn)]' },
  }[tone];
  return (
    <div className="card-sm flex flex-col gap-1">
      <p className="text-xs text-[var(--tx-3)] font-medium uppercase tracking-wide">{label}</p>
      <p className={cn('text-2xl font-bold tracking-tight', colors.value)}>{value}</p>
      {sub && <p className="text-xs text-[var(--tx-3)]">{sub}</p>}
    </div>
  );
}

// ── Chart section wrapper ─────────────────────────────────────────────────────

function ChartSection({ title, chartRef, rows, columns, children }: {
  title: string;
  chartRef: React.RefObject<HTMLDivElement>;
  /** The series behind the chart — exported as the data table / worksheet. */
  rows: Array<Record<string, unknown>>;
  columns?: string[];
  children: React.ReactNode;
}) {
  const [busy, setBusy] = useState<AnalyticsFormat | 'png' | null>(null);
  const [error, setError] = useState<string | null>(null);
  const slug = title.replace(/\s+/g, '_').toLowerCase();

  const run = async (format: AnalyticsFormat | 'png') => {
    setBusy(format);
    setError(null);
    try {
      if (format === 'png') {
        await downloadChartAsPng(chartRef, slug);
        return;
      }
      // Strip the colour key — it drives rendering, not reporting.
      const clean = rows.map(({ color: _color, ...rest }) => rest);
      await exportAnalytics(
        {
          title,
          filename: slug,
          generated_at: new Date().toLocaleString(),
          charts: [{
            title,
            columns: columns ?? (clean[0] ? Object.keys(clean[0]) : []),
            rows: clean,
            image: format === 'pdf' ? await chartToPngDataUrl(chartRef) : null,
          }],
        },
        format,
      );
    } catch (e) {
      setError(extractError(e).message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="card-sm flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <h3 className="text-sm font-semibold text-[var(--tx)]">{title}</h3>
        <div className="flex items-center gap-1">
          <svg className="h-3.5 w-3.5 text-[var(--tx-3)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3" />
          </svg>
          {([['png', 'PNG'], ['pdf', 'PDF'], ['xlsx', 'Excel']] as const).map(([fmt, label]) => (
            <button
              key={fmt}
              onClick={() => run(fmt)}
              disabled={busy !== null}
              className="btn-ghost !py-1 !px-2 text-xs disabled:opacity-50"
              title={`Download this chart as ${label}`}
            >
              {busy === fmt ? '…' : label}
            </button>
          ))}
        </div>
      </div>
      {error && <p className="text-xs text-[var(--err)]">{error}</p>}
      <div ref={chartRef}>{children}</div>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export function ReportsPage() {
  const [format, setFormat] = useState<ReportFormat>('csv');
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [priorityFilter, setPriorityFilter] = useState('');
  const [downloading, setDownloading] = useState(false);
  const [exporting, setExporting] = useState<AnalyticsFormat | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const barRef = useRef<HTMLDivElement>(null);
  const pieRef = useRef<HTMLDivElement>(null);
  const lineRef = useRef<HTMLDivElement>(null);
  const priorityRef = useRef<HTMLDivElement>(null);

  // Fetch dashboard data for charts (parallel from real endpoints)
  const { data: kpis } = useQuery({
    queryKey: ['dashboard-kpis'],
    queryFn: async () => { const r = await api.get('/dashboard/kpis'); return r.data.data; },
  });
  const { data: categoryDist = [] } = useQuery({
    queryKey: ['dashboard-categories'],
    queryFn: async () => { const r = await api.get('/dashboard/category-distribution'); return r.data.data; },
  });
  const { data: deptLoad = [] } = useQuery({
    queryKey: ['dashboard-dept-load'],
    queryFn: async () => { const r = await api.get('/dashboard/department-load'); return r.data.data; },
  });
  const { data: recentTickets = [] } = useQuery({
    queryKey: ['dashboard-recent'],
    queryFn: async () => { const r = await api.get('/dashboard/recent-tickets'); return r.data.data; },
  });
  const { data: trend = [] } = useQuery({
    queryKey: ['dashboard-trend'],
    queryFn: async () => { const r = await api.get('/dashboard/ticket-trend', { params: { days: 30 } }); return r.data.data; },
  });

  const handleDownload = async () => {
    setDownloading(true);
    setDownloadError(null);
    try {
      await downloadTicketReport({
        format,
        from_date: fromDate || undefined,
        to_date: toDate || undefined,
        status: statusFilter || undefined,
        priority: priorityFilter || undefined,
      });
    } catch (e) {
      // `extractError` reads this API's envelope, `{error: {message}}`. The
      // previous `e.response.data.detail` is FastAPI's default shape, which
      // this app does not return — so the server's real message was never
      // shown and every failure read "Download failed. Please try again."
      setDownloadError(extractError(e).message);
    } finally {
      setDownloading(false);
    }
  };

  // Derive status distribution from recent tickets (best available without a dedicated endpoint)
  const statusCounts: Record<string, number> = {};
  recentTickets.forEach((t: { status: string }) => {
    statusCounts[t.status] = (statusCounts[t.status] || 0) + 1;
  });
  const byStatus: Array<{ name: string; count: number; color: string }> =
    Object.entries(statusCounts).map(([name, count]) => ({
      name: name.replace(/_/g, ' '),
      count,
      color: STATUS_COLORS[name] ?? '#6B7280',
    }));

  // Category distribution → use as pseudo "priority/type" breakdown
  const byPriority: Array<{ name: string; value: number; color: string }> =
    (categoryDist as Array<{ category: string; count: number }>).slice(0, 6).map((d, i) => ({
      name: d.category,
      value: d.count,
      color: Object.values(PRIORITY_COLORS)[i % 4],
    }));

  // Real daily series. This used to plot department load with a date axis
  // label — a bar per department under a "Tickets Over Time" heading.
  const byDay: Array<{ date: string; created: number; resolved: number; count: number }> =
    (trend as Array<{ date: string; created: number; resolved: number; count: number }>).map(d => ({
      // Short axis label: "10 Aug" reads better than an ISO date at this width.
      date: new Date(d.date).toLocaleDateString(undefined, { day: 'numeric', month: 'short' }),
      created: d.created,
      resolved: d.resolved,
      count: d.count,
    }));

  // SLA compliance by department (derived from breached_count / open_count)
  const slaByDept: Array<{ name: string; compliance: number }> =
    (deptLoad as Array<{ department: string; open_count: number; breached_count: number }>).map(d => ({
      name: d.department,
      compliance: d.open_count > 0
        ? Math.round(((d.open_count - d.breached_count) / d.open_count) * 100)
        : 100,
    }));

  const totalTickets = (kpis?.open_tickets ?? 0) + (kpis?.resolved_today ?? 0);
  const openTickets = kpis?.open_tickets ?? 0;
  const slaBreached = kpis?.sla_breached ?? 0;
  const avgResolutionHrs: number | null = kpis?.avg_resolution_hours ?? null;

  /** One document containing every KPI tile and every chart on the page. */
  const exportDashboard = async (format: AnalyticsFormat) => {
    setExporting(format);
    setExportError(null);
    try {
      const strip = (rows: Array<Record<string, unknown>>) =>
        rows.map(({ color: _color, ...rest }) => rest);

      const sections: Array<[string, React.RefObject<HTMLDivElement>, Array<Record<string, unknown>>, string[]]> = [
        ['Tickets by Status', barRef, byStatus, ['name', 'count']],
        ['Tickets by Priority', priorityRef, byPriority, ['name', 'value']],
        ['Tickets Over Time', lineRef, byDay, ['date', 'count']],
        ['SLA Compliance by Department', pieRef, slaByDept, ['name', 'compliance']],
      ];

      // Images only go in the PDF — a workbook has nowhere to put them.
      const charts = await Promise.all(
        sections.map(async ([title, ref, rows, columns]) => ({
          title,
          columns,
          rows: strip(rows),
          image: format === 'pdf' ? await chartToPngDataUrl(ref) : null,
        })),
      );

      await exportAnalytics(
        {
          title: 'SUCCESS Bank — Ticket Analytics',
          filename: 'ticket_analytics',
          generated_at: new Date().toLocaleString(),
          kpis: [
            { label: 'Total tickets', value: totalTickets },
            { label: 'Open tickets', value: openTickets },
            { label: 'SLA breached', value: slaBreached },
            {
              label: 'Average resolution (hours)',
              value: avgResolutionHrs != null ? avgResolutionHrs.toFixed(1) : '—',
            },
          ],
          charts,
        },
        format,
      );
    } catch (e) {
      setExportError(extractError(e).message);
    } finally {
      setExporting(null);
    }
  };

  return (
    <PageShell>
      <PageHeader
        title="Reports"
        subtitle="Download audit reports and visualise ticket metrics."
      />

      {/* KPIs */}
      <div className="flex items-center justify-between gap-2 flex-wrap -mb-1">
        <h2 className="text-sm font-semibold text-[var(--tx)]">Key metrics</h2>
        <div className="flex items-center gap-1">
          <span className="text-xs text-[var(--tx-3)] mr-1">Export everything</span>
          {([['pdf', 'PDF'], ['xlsx', 'Excel']] as const).map(([fmt, label]) => (
            <button
              key={fmt}
              onClick={() => exportDashboard(fmt)}
              disabled={exporting !== null}
              className="btn-ghost !py-1 !px-2 text-xs disabled:opacity-50"
            >
              {exporting === fmt ? 'Preparing…' : label}
            </button>
          ))}
        </div>
      </div>
      {exportError && <p className="text-xs text-[var(--err)] -mt-2">{exportError}</p>}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard label="Total Tickets" value={totalTickets} />
        <StatCard label="Open" value={openTickets} tone="warning" />
        <StatCard label="SLA Breached" value={slaBreached} tone="danger" />
        <StatCard
          label="Avg Resolution"
          value={avgResolutionHrs != null ? `${avgResolutionHrs.toFixed(1)}h` : '—'}
          tone="success"
        />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ChartSection title="Tickets by Status" chartRef={barRef} rows={byStatus} columns={['name', 'count']}>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={byStatus} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--sh-dark)" />
              <XAxis dataKey="name" tick={{ fontSize: 10, fill: 'var(--tx-3)' }} />
              <YAxis tick={{ fontSize: 10, fill: 'var(--tx-3)' }} />
              <Tooltip contentStyle={{ background: 'var(--inset)', border: '1px solid var(--sh-dark)', borderRadius: 8, fontSize: 12 }} />
              <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                {byStatus.map((entry, i) => (
                  <Cell key={i} fill={entry.color} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartSection>

        <ChartSection title="Tickets by Priority" chartRef={priorityRef} rows={byPriority} columns={['name', 'value']}>
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie data={byPriority} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80} label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`} labelLine={false}>
                {byPriority.map((entry, i) => (
                  <Cell key={i} fill={entry.color} />
                ))}
              </Pie>
              <Legend iconSize={10} wrapperStyle={{ fontSize: 11 }} />
              <Tooltip contentStyle={{ background: 'var(--inset)', border: '1px solid var(--sh-dark)', borderRadius: 8, fontSize: 12 }} />
            </PieChart>
          </ResponsiveContainer>
        </ChartSection>

        <ChartSection title="Tickets Over Time" chartRef={lineRef} rows={byDay} columns={['date', 'created', 'resolved']}>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={byDay} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--sh-dark)" />
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: 'var(--tx-3)' }} />
              <YAxis tick={{ fontSize: 10, fill: 'var(--tx-3)' }} />
              <Tooltip contentStyle={{ background: 'var(--inset)', border: '1px solid var(--sh-dark)', borderRadius: 8, fontSize: 12 }} />
              <Legend iconSize={10} wrapperStyle={{ fontSize: 11 }} />
              <Line type="monotone" dataKey="created" name="Created" stroke="var(--brand)" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="resolved" name="Resolved" stroke="#10B981" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </ChartSection>

        <ChartSection title="SLA Compliance by Department" chartRef={pieRef} rows={slaByDept} columns={['name', 'compliance']}>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={slaByDept} layout="vertical" margin={{ top: 4, right: 8, left: 60, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--sh-dark)" />
              <XAxis type="number" domain={[0, 100]} tickFormatter={v => `${v}%`} tick={{ fontSize: 10, fill: 'var(--tx-3)' }} />
              <YAxis type="category" dataKey="name" tick={{ fontSize: 10, fill: 'var(--tx-3)' }} width={56} />
              <Tooltip formatter={(v: number) => `${v.toFixed(1)}%`} contentStyle={{ background: 'var(--inset)', border: '1px solid var(--sh-dark)', borderRadius: 8, fontSize: 12 }} />
              <Bar dataKey="compliance" radius={[0, 4, 4, 0]}>
                {slaByDept.map((entry, i) => (
                  <Cell key={i} fill={entry.compliance >= 90 ? '#10B981' : entry.compliance >= 75 ? '#F59E0B' : '#EF4444'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartSection>
      </div>

      {/* Download panel */}
      <div className="card-sm !p-5">
        <h2 className="text-sm font-semibold text-[var(--tx)] mb-4">Download Audit Report</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-4">
          <label className="flex flex-col gap-1 text-sm font-medium text-[var(--tx-2)]">
            Format
            <select className="input" value={format} onChange={e => setFormat(e.target.value as ReportFormat)}>
              <option value="csv">CSV (spreadsheet)</option>
              <option value="xlsx">Excel (.xlsx)</option>
              <option value="pdf">PDF</option>
            </select>
          </label>
          <label className="flex flex-col gap-1 text-sm font-medium text-[var(--tx-2)]">
            From Date
            <input type="datetime-local" className="input" value={fromDate} onChange={e => setFromDate(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1 text-sm font-medium text-[var(--tx-2)]">
            To Date
            <input type="datetime-local" className="input" value={toDate} onChange={e => setToDate(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1 text-sm font-medium text-[var(--tx-2)]">
            Status Filter
            <select className="input" value={statusFilter} onChange={e => setStatusFilter(e.target.value)}>
              <option value="">All statuses</option>
              {['new','acknowledged','assigned','in_progress','on_hold','escalated','resolved','closed','reopened'].map(s => (
                <option key={s} value={s}>{s.replace('_', ' ')}</option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-sm font-medium text-[var(--tx-2)]">
            Priority Filter
            <select className="input" value={priorityFilter} onChange={e => setPriorityFilter(e.target.value)}>
              <option value="">All priorities</option>
              {['critical','high','medium','low'].map(p => <option key={p} value={p}>{p}</option>)}
            </select>
          </label>
        </div>

        {downloadError && (
          <div className="mb-3 text-xs text-[var(--err)] card-sm !p-2" style={{ borderLeft: '3px solid var(--err)' }}>{downloadError}</div>
        )}

        <div className="flex items-center gap-3">
          <Button onClick={handleDownload} disabled={downloading}>
            {downloading ? (
              <>
                <div className="h-3.5 w-3.5 rounded-full border-2 border-white border-t-transparent animate-spin" />
                Generating…
              </>
            ) : (
              <>
                <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3" />
                </svg>
                Download {format.toUpperCase()}
              </>
            )}
          </Button>
          <p className="text-xs text-[var(--tx-3)]">
            Includes: ticket ID, raised/resolved time, org code, hierarchy chain, AI assist, escalation count, SLA data, reopen count, and more.
          </p>
        </div>
      </div>
    </PageShell>
  );
}
