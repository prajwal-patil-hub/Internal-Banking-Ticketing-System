import { useState, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend, LineChart, Line,
} from 'recharts';
import { Button } from '@/components/Button';
import { cn } from '@/lib/cn';
import { downloadTicketReport, type ReportFormat } from '@/features/reports/api';
import { api } from '@/lib/api';

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

function downloadChartAsPng(ref: React.RefObject<HTMLDivElement>, name: string) {
  const svg = ref.current?.querySelector('svg');
  if (!svg) return;

  const serializer = new XMLSerializer();
  const svgStr = serializer.serializeToString(svg);
  const svgBlob = new Blob([svgStr], { type: 'image/svg+xml;charset=utf-8' });
  const svgUrl = URL.createObjectURL(svgBlob);

  const img = new Image();
  img.onload = () => {
    const canvas = document.createElement('canvas');
    canvas.width = svg.clientWidth * 2;
    canvas.height = svg.clientHeight * 2;
    const ctx = canvas.getContext('2d')!;
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    const pngUrl = canvas.toDataURL('image/png');
    const a = document.createElement('a');
    a.href = pngUrl;
    a.download = `${name}.png`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(svgUrl);
  };
  img.src = svgUrl;
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

function ChartSection({ title, chartRef, children }: {
  title: string;
  chartRef: React.RefObject<HTMLDivElement>;
  children: React.ReactNode;
}) {
  return (
    <div className="card-sm flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-[var(--tx)]">{title}</h3>
        <button
          onClick={() => downloadChartAsPng(chartRef, title.replace(/\s+/g, '_').toLowerCase())}
          className="btn-ghost !py-1 !px-2 text-xs gap-1"
        >
          <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3" />
          </svg>
          PNG
        </button>
      </div>
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
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const barRef = useRef<HTMLDivElement>(null);
  const pieRef = useRef<HTMLDivElement>(null);
  const lineRef = useRef<HTMLDivElement>(null);
  const priorityRef = useRef<HTMLDivElement>(null);

  // Fetch dashboard data for charts
  const { data: dashData } = useQuery({
    queryKey: ['dashboard-stats'],
    queryFn: async () => {
      const res = await api.get('/dashboard/stats');
      return res.data.data;
    },
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
    } catch (e: any) {
      setDownloadError(e?.response?.data?.detail ?? 'Download failed. Please try again.');
    } finally {
      setDownloading(false);
    }
  };

  const byStatus: Array<{ name: string; count: number; color: string }> =
    Object.entries(dashData?.tickets_by_status ?? {}).map(([name, count]) => ({
      name: name.replace('_', ' '),
      count: count as number,
      color: STATUS_COLORS[name] ?? '#6B7280',
    }));

  const byPriority: Array<{ name: string; value: number; color: string }> =
    Object.entries(dashData?.tickets_by_priority ?? {}).map(([name, value]) => ({
      name,
      value: value as number,
      color: PRIORITY_COLORS[name] ?? '#6B7280',
    }));

  const byDay: Array<{ date: string; count: number }> = dashData?.tickets_over_time ?? [];

  const slaByDept: Array<{ name: string; compliance: number }> = (dashData?.department_sla ?? []).map(
    (d: { department: string; compliance: number }) => ({ name: d.department, compliance: d.compliance })
  );

  const totalTickets = dashData?.totals?.total ?? 0;
  const openTickets = dashData?.totals?.open ?? 0;
  const slaBreached = dashData?.totals?.sla_breached ?? 0;
  const avgResolutionHrs = dashData?.totals?.avg_resolution_hrs ?? null;

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-[var(--tx)]">Reports</h1>
        <p className="text-xs text-[var(--tx-3)] mt-0.5">Download audit reports and visualize ticket metrics.</p>
      </div>

      {/* KPIs */}
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
        <ChartSection title="Tickets by Status" chartRef={barRef}>
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

        <ChartSection title="Tickets by Priority" chartRef={priorityRef}>
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

        <ChartSection title="Tickets Over Time" chartRef={lineRef}>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={byDay} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--sh-dark)" />
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: 'var(--tx-3)' }} />
              <YAxis tick={{ fontSize: 10, fill: 'var(--tx-3)' }} />
              <Tooltip contentStyle={{ background: 'var(--inset)', border: '1px solid var(--sh-dark)', borderRadius: 8, fontSize: 12 }} />
              <Line type="monotone" dataKey="count" stroke="var(--brand)" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </ChartSection>

        <ChartSection title="SLA Compliance by Department" chartRef={pieRef}>
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
    </div>
  );
}
