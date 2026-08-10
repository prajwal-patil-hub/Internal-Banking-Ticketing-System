import { api } from '@/lib/api';

export type ReportFormat = 'csv' | 'xlsx' | 'pdf';

export interface ReportFilters {
  format: ReportFormat;
  from_date?: string;
  to_date?: string;
  status?: string;
  priority?: string;
  org_unit_id?: string;
}

export async function downloadTicketReport(filters: ReportFilters): Promise<void> {
  const { format, ...rest } = filters;
  const params: Record<string, string> = { format };
  for (const [k, v] of Object.entries(rest)) {
    if (v != null && v !== '') params[k] = String(v);
  }

  const res = await api.get('/reports/tickets', {
    params,
    responseType: 'blob',
  });

  const mimeMap: Record<ReportFormat, string> = {
    csv:  'text/csv',
    xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    pdf:  'application/pdf',
  };

  const url = URL.createObjectURL(new Blob([res.data], { type: mimeMap[format] }));
  const a = document.createElement('a');
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
  a.href = url;
  a.download = `ticket_report_${timestamp}.${format}`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ── Dashboard analytics export ───────────────────────────────────────────────
//
// Charts could previously only be saved as a PNG rendered in the browser.
// PDF and Excel are produced server-side from the data the page is already
// displaying, reusing the report libraries the backend has — that keeps the
// export consistent with what the user sees and adds nothing to the bundle.

export type AnalyticsFormat = 'pdf' | 'xlsx';

export interface AnalyticsChart {
  title: string;
  /** Column order; inferred from the first row when omitted. */
  columns?: string[];
  rows: Array<Record<string, unknown>>;
  /** Optional `data:image/png;base64,...` of the rendered chart. */
  image?: string | null;
}

export interface AnalyticsPayload {
  title?: string;
  filename?: string;
  generated_at?: string;
  kpis?: Array<{ label: string; value: string | number }>;
  charts?: AnalyticsChart[];
}

export async function exportAnalytics(
  payload: AnalyticsPayload,
  format: AnalyticsFormat,
): Promise<void> {
  const res = await api.post('/reports/analytics', payload, {
    params: { format },
    responseType: 'blob',
    // Embedded chart images make these payloads large and the PDF build is
    // not instant; the default 15s budget is too tight.
    timeout: 60_000,
  });

  const mime =
    format === 'pdf'
      ? 'application/pdf'
      : 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';

  const url = URL.createObjectURL(new Blob([res.data], { type: mime }));
  const a = document.createElement('a');
  const stamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
  a.href = url;
  a.download = `${payload.filename ?? 'dashboard'}_${stamp}.${format}`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
