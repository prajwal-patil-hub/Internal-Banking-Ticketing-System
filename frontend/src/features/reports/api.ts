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
