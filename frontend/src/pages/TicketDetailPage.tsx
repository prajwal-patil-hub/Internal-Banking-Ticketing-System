import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Button } from '@/components/Button';
import { Badge } from '@/components/Badge';
import { StatusBadge } from '@/components/StatusBadge';
import { PriorityBadge } from '@/components/PriorityBadge';
import { SLABadge } from '@/components/SLABadge';
import { AIBadge } from '@/components/AIBadge';
import { useAuth } from '@/store/auth';
import { cn } from '@/lib/cn';
import {
  getTicket,
  getComments,
  addComment,
  updateTicketStatus,
  aiSummarize,
  aiSuggest,
  pauseSLA,
  resumeSLA,
  getAuditLog,
} from '@/features/tickets/api';
import type { Ticket, Comment, TicketStatus } from '@/features/tickets/api';

const STALE = 30_000;

// ── FSM ───────────────────────────────────────────────────────────────────────

const STATUS_TRANSITIONS: Record<TicketStatus, TicketStatus[]> = {
  new:          ['acknowledged', 'assigned', 'closed'],
  acknowledged: ['assigned', 'in_progress', 'closed'],
  assigned:     ['in_progress', 'on_hold', 'escalated'],
  in_progress:  ['on_hold', 'escalated', 'resolved'],
  on_hold:      ['in_progress', 'escalated', 'closed'],
  escalated:    ['in_progress', 'resolved'],
  resolved:     ['closed', 'reopened'],
  closed:       ['reopened'],
  reopened:     ['acknowledged', 'assigned', 'in_progress'],
};

const STATUS_LABELS: Record<TicketStatus, string> = {
  new:          'Mark New',
  acknowledged: 'Acknowledge',
  assigned:     'Assign',
  in_progress:  'Start Work',
  on_hold:      'Put On Hold',
  escalated:    'Escalate',
  resolved:     'Resolve',
  closed:       'Close',
  reopened:     'Reopen',
};

const STATUS_VARIANTS: Partial<Record<TicketStatus, 'primary' | 'ghost' | 'danger'>> = {
  escalated: 'danger',
  closed:    'ghost',
  resolved:  'primary',
};

// ── Skeletons ─────────────────────────────────────────────────────────────────

function Sk({ className }: { className?: string }) {
  return <div className={cn('animate-pulse rounded-lg bg-slate-200 dark:bg-slate-800', className)} />;
}

function DetailSkeleton() {
  return (
    <div className="flex flex-col gap-4">
      <Sk className="h-6 w-64" />
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <div className="xl:col-span-2 flex flex-col gap-4">
          <Sk className="h-40" />
          <Sk className="h-32" />
        </div>
        <div className="flex flex-col gap-4">
          <Sk className="h-48" />
          <Sk className="h-28" />
        </div>
      </div>
    </div>
  );
}

// ── Comment ───────────────────────────────────────────────────────────────────

function CommentItem({ comment }: { comment: Comment }) {
  const date = new Date(comment.created_at);
  const timeStr = date.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }) +
    ' ' + date.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });

  return (
    <div className={cn(
      'flex flex-col gap-1.5 p-3 rounded-lg border text-sm',
      comment.is_internal
        ? 'bg-amber-50 border-amber-200 dark:bg-amber-900/10 dark:border-amber-800/40'
        : 'bg-white border-slate-100 dark:bg-slate-800/60 dark:border-slate-700/60',
    )}>
      <div className="flex items-center gap-2">
        <div className="h-6 w-6 rounded-full bg-brand-100 dark:bg-brand-900/40 flex items-center justify-center text-brand-700 dark:text-brand-300 text-[10px] font-bold shrink-0">
          {comment.author_id?.slice(0, 2).toUpperCase() ?? 'SY'}
        </div>
        <span className="text-xs font-medium text-slate-700 dark:text-slate-300">
          {comment.author_id ? `Agent #${comment.author_id.slice(0, 6)}` : 'System'}
        </span>
        {comment.is_internal && (
          <Badge tone="warning" className="text-[9px] py-0.5 px-1.5">Internal</Badge>
        )}
        {comment.ai_generated && (
          <Badge tone="info" className="text-[9px] py-0.5 px-1.5">AI</Badge>
        )}
        <span className="text-[10px] text-slate-400 ml-auto">{timeStr}</span>
      </div>
      <p className="text-sm text-slate-700 dark:text-slate-300 whitespace-pre-wrap leading-relaxed pl-8">
        {comment.body}
      </p>
    </div>
  );
}

// ── Audit row ─────────────────────────────────────────────────────────────────

const ACTION_CLS: Record<string, string> = {
  create:        'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400',
  update:        'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  delete:        'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
  status_change: 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400',
  assign:        'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400',
};

function AuditRow({ entry }: { entry: { id: string; action: string; actor_email: string | null; entity_type: string; created_at: string; old_values: Record<string, unknown> | null; new_values: Record<string, unknown> | null } }) {
  const [expanded, setExpanded] = useState(false);
  const date = new Date(entry.created_at);
  const timeStr = date.toLocaleDateString('en-GB', { day: '2-digit', month: 'short' }) +
    ' ' + date.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
  const cls = ACTION_CLS[entry.action] ?? 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400';

  return (
    <>
      <tr
        className="border-b border-slate-50 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/30 cursor-pointer transition-colors"
        onClick={() => setExpanded((p) => !p)}
      >
        <td className="px-4 py-2 text-[11px] text-slate-500 whitespace-nowrap">{timeStr}</td>
        <td className="px-4 py-2 text-[11px] font-medium text-slate-700 dark:text-slate-300">{entry.actor_email ?? 'System'}</td>
        <td className="px-4 py-2">
          <span className={cn('pill text-[10px]', cls)}>{entry.action}</span>
        </td>
        <td className="px-4 py-2 text-right">
          {(entry.old_values || entry.new_values) && (
            <svg className={cn('h-3 w-3 text-slate-400 inline-block transition-transform', expanded && 'rotate-180')} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M6 9l6 6 6-6" />
            </svg>
          )}
        </td>
      </tr>
      {expanded && (entry.old_values || entry.new_values) && (
        <tr className="bg-slate-50 dark:bg-slate-900/50">
          <td colSpan={4} className="px-4 py-3">
            <div className="grid grid-cols-2 gap-3 text-xs">
              {entry.old_values && (
                <div>
                  <p className="font-medium text-slate-400 mb-1 text-[10px] uppercase tracking-wide">Before</p>
                  <pre className="bg-white dark:bg-slate-800 rounded-lg p-2 overflow-x-auto text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-700 text-[10px]">
                    {JSON.stringify(entry.old_values, null, 2)}
                  </pre>
                </div>
              )}
              {entry.new_values && (
                <div>
                  <p className="font-medium text-slate-400 mb-1 text-[10px] uppercase tracking-wide">After</p>
                  <pre className="bg-white dark:bg-slate-800 rounded-lg p-2 overflow-x-auto text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-700 text-[10px]">
                    {JSON.stringify(entry.new_values, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

// ── Metadata row ──────────────────────────────────────────────────────────────

function MetaRow({ label, value, mono = false }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <div className="flex items-start justify-between gap-2 py-1.5 border-b border-slate-50 dark:border-slate-800/60 last:border-b-0">
      <span className="text-[11px] text-slate-400 uppercase tracking-wide font-medium shrink-0">{label}</span>
      <span className={cn('text-xs text-slate-700 dark:text-slate-300 text-right', mono && 'font-mono truncate max-w-[140px]')} title={typeof value === 'string' ? value : undefined}>
        {value ?? <span className="text-slate-300 dark:text-slate-600">—</span>}
      </span>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export function TicketDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const queryClient = useQueryClient();

  const [commentText, setCommentText] = useState('');
  const [isInternal, setIsInternal] = useState(false);
  const [aiSummaryResult, setAISummaryResult] = useState<{ summary: string; sentiment: string; risk_score: number } | null>(null);
  const [aiSuggestResult, setAISuggestResult] = useState<{ suggestions: string[]; next_actions: string[] } | null>(null);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [aiExpanded, setAiExpanded] = useState(false);

  const isAgent = ['admin', 'agent', 'supervisor', 'auditor'].includes(user?.role ?? '');

  const ticketQuery   = useQuery({ queryKey: ['tickets', id],                  queryFn: () => getTicket(id!),                                        enabled: !!id, staleTime: STALE });
  const commentsQuery = useQuery({ queryKey: ['tickets', id, 'comments', isAgent], queryFn: () => getComments(id!, isAgent),                         enabled: !!id, staleTime: STALE });
  const auditQuery    = useQuery({ queryKey: ['audit', 'ticket', id],           queryFn: () => getAuditLog({ entity_type: 'ticket', page: 1, page_size: 15 }), enabled: !!id && isAgent, staleTime: STALE });

  const statusMutation  = useMutation({ mutationFn: ({ status, comment }: { status: TicketStatus; comment?: string }) => updateTicketStatus(id!, status, comment), onSuccess: (updated) => queryClient.setQueryData(['tickets', id], updated) });
  const commentMutation = useMutation({ mutationFn: () => addComment(id!, commentText, isInternal), onSuccess: () => { setCommentText(''); queryClient.invalidateQueries({ queryKey: ['tickets', id, 'comments'] }); } });
  const summarizeMutation = useMutation({ mutationFn: () => aiSummarize(id!), onSuccess: (r) => { setAISummaryResult(r); setAiExpanded(true); } });
  const suggestMutation   = useMutation({ mutationFn: () => aiSuggest(id!),   onSuccess: (r) => { setAISuggestResult(r); setShowSuggestions(true); setAiExpanded(true); } });
  const pauseSLAMutation  = useMutation({ mutationFn: () => pauseSLA(id!),    onSuccess: (u) => queryClient.setQueryData(['tickets', id], u) });
  const resumeSLAMutation = useMutation({ mutationFn: () => resumeSLA(id!),   onSuccess: (u) => queryClient.setQueryData(['tickets', id], u) });

  if (ticketQuery.isLoading) return <DetailSkeleton />;

  if (ticketQuery.isError || !ticketQuery.data) {
    return (
      <div className="flex flex-col items-center gap-3 py-16 text-center bg-white dark:bg-slate-900 rounded-xl border border-slate-200/80 dark:border-slate-800">
        <svg className="h-10 w-10 text-red-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10" /><path d="M12 8v4M12 16h.01" />
        </svg>
        <p className="text-sm font-medium">Ticket not found</p>
        <p className="text-xs text-slate-400">This ticket doesn't exist or you don't have access.</p>
        <Button variant="ghost" onClick={() => navigate('/tickets')}>Back to Tickets</Button>
      </div>
    );
  }

  const ticket: Ticket = ticketQuery.data;
  const comments: Comment[] = commentsQuery.data ?? [];
  const availableTransitions = STATUS_TRANSITIONS[ticket.status] ?? [];
  const hasAI = !!(ticket.ai_summary || aiSummaryResult || aiSuggestResult);

  function fmtDate(d: string | null): string {
    if (!d) return '—';
    return new Date(d).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  }

  return (
    <div className="flex flex-col gap-4">

      {/* ── Breadcrumb ───────────────────────────────────────────────── */}
      <div className="flex items-center gap-2 text-xs">
        <button onClick={() => navigate('/tickets')} className="text-brand-600 hover:underline dark:text-brand-400">
          Tickets
        </button>
        <span className="text-slate-300 dark:text-slate-700">/</span>
        <span className="font-mono text-slate-500 dark:text-slate-400">{ticket.ticket_number}</span>
      </div>

      {/* ── Title + status row ───────────────────────────────────────── */}
      <div className="flex items-start gap-4">
        <div className="flex-1 min-w-0">
          {/* Badges row */}
          <div className="flex items-center gap-1.5 flex-wrap mb-2">
            <span className="font-mono text-xs font-bold text-brand-600 dark:text-brand-400 bg-brand-50 dark:bg-brand-900/20 px-2 py-0.5 rounded">
              {ticket.ticket_number}
            </span>
            <StatusBadge status={ticket.status} />
            <PriorityBadge priority={ticket.priority} />
            <SLABadge breached={ticket.sla_breached} dueAt={ticket.resolution_due_at} />
            {(ticket.ai_category || ticket.ai_risk_score !== null) && (
              <AIBadge category={ticket.ai_category} confidence={ticket.ai_confidence} riskScore={ticket.ai_risk_score} />
            )}
          </div>
          <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100 leading-snug">
            {ticket.title}
          </h1>
        </div>

        {/* Action buttons (agent only) */}
        {isAgent && availableTransitions.length > 0 && (
          <div className="flex items-center gap-1.5 flex-wrap shrink-0">
            {availableTransitions.map((next) => (
              <Button
                key={next}
                variant={STATUS_VARIANTS[next] ?? 'ghost'}
                disabled={statusMutation.isPending}
                onClick={() => statusMutation.mutate({ status: next })}
              >
                {STATUS_LABELS[next]}
              </Button>
            ))}
          </div>
        )}
      </div>

      {/* ── Main layout ─────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">

        {/* ── Left column ─────────────────────────────────────────────── */}
        <div className="xl:col-span-2 flex flex-col gap-4">

          {/* Description */}
          <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200/80 dark:border-slate-800 p-4">
            <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-2.5">Description</h2>
            <p className="text-sm text-slate-600 dark:text-slate-400 leading-relaxed whitespace-pre-wrap">
              {ticket.description}
            </p>
            {ticket.email_from && (
              <div className="mt-3 pt-2.5 border-t border-slate-100 dark:border-slate-800 text-xs text-slate-500">
                From: <span className="font-mono text-slate-600 dark:text-slate-400">{ticket.email_from}</span>
              </div>
            )}
          </div>

          {/* AI Insights (collapsible) */}
          <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200/80 dark:border-slate-800 overflow-hidden">
            {/* AI header */}
            <div className="flex items-center gap-2 px-4 py-3 border-b border-slate-100 dark:border-slate-800">
              <div className="h-5 w-5 rounded bg-accent-100 dark:bg-accent-500/20 flex items-center justify-center shrink-0">
                <svg className="h-3 w-3 text-accent-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 2a10 10 0 0 1 0 20M12 2a10 10 0 0 0 0 20M12 8v4M12 16h.01" />
                </svg>
              </div>
              <span className="text-sm font-semibold text-slate-700 dark:text-slate-300 flex-1">AI Insights</span>

              <div className="flex items-center gap-1.5">
                <Button
                  variant="ghost"
                  disabled={summarizeMutation.isPending}
                  onClick={() => summarizeMutation.mutate()}
                >
                  {summarizeMutation.isPending ? (
                    <svg className="h-3 w-3 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83" strokeLinecap="round" />
                    </svg>
                  ) : null}
                  {summarizeMutation.isPending ? 'Summarizing…' : 'Summarize'}
                </Button>
                <Button
                  variant="ghost"
                  disabled={suggestMutation.isPending}
                  onClick={() => suggestMutation.mutate()}
                >
                  {suggestMutation.isPending ? 'Analyzing…' : 'Suggestions'}
                </Button>
                {hasAI && (
                  <button
                    onClick={() => setAiExpanded((p) => !p)}
                    className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
                    aria-expanded={aiExpanded}
                    title={aiExpanded ? 'Collapse' : 'Expand'}
                  >
                    <svg className={cn('h-3.5 w-3.5 transition-transform', aiExpanded && 'rotate-180')} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M6 9l6 6 6-6" />
                    </svg>
                  </button>
                )}
              </div>
            </div>

            {/* AI content */}
            {!hasAI ? (
              <p className="text-xs text-slate-400 italic px-4 py-3">
                Click "Summarize" or "Suggestions" to run AI analysis.
              </p>
            ) : aiExpanded ? (
              <div className="p-4 flex flex-col gap-3">
                {/* Existing summary from DB */}
                {ticket.ai_summary && !aiSummaryResult && (
                  <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700">
                    <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wide mb-1">AI Summary</p>
                    <p className="text-xs text-slate-700 dark:text-slate-300">{ticket.ai_summary}</p>
                  </div>
                )}
                {/* Fresh summary */}
                {aiSummaryResult && (
                  <div className="p-3 rounded-lg bg-accent-50 dark:bg-accent-500/10 border border-accent-200 dark:border-accent-500/20">
                    <div className="flex items-center gap-2 mb-1.5">
                      <p className="text-[10px] font-semibold text-accent-600 dark:text-accent-400 uppercase tracking-wide">Summary</p>
                      <span className={cn('pill text-[9px]',
                        aiSummaryResult.sentiment === 'positive' ? 'bg-emerald-100 text-emerald-700' :
                        aiSummaryResult.sentiment === 'negative' ? 'bg-red-100 text-red-700' : 'bg-slate-100 text-slate-600'
                      )}>{aiSummaryResult.sentiment}</span>
                      <span className={cn('pill text-[9px]',
                        aiSummaryResult.risk_score >= 0.7 ? 'bg-red-100 text-red-700' :
                        aiSummaryResult.risk_score >= 0.3 ? 'bg-amber-100 text-amber-700' : 'bg-emerald-100 text-emerald-700'
                      )}>Risk {(aiSummaryResult.risk_score * 100).toFixed(0)}%</span>
                    </div>
                    <p className="text-xs text-slate-700 dark:text-slate-300">{aiSummaryResult.summary}</p>
                  </div>
                )}
                {/* Suggestions */}
                {aiSuggestResult && showSuggestions && (
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wide">Suggestions</p>
                      <button onClick={() => setShowSuggestions(false)} className="text-[10px] text-slate-400 hover:text-slate-600">Hide</button>
                    </div>
                    <div className="flex flex-col gap-2">
                      {aiSuggestResult.suggestions.map((s, i) => (
                        <div key={i} className="flex items-start gap-2 text-xs text-slate-700 dark:text-slate-300">
                          <span className="h-4 w-4 rounded-full bg-brand-100 text-brand-700 flex items-center justify-center text-[9px] font-bold shrink-0 mt-0.5">{i + 1}</span>
                          {s}
                        </div>
                      ))}
                      {aiSuggestResult.next_actions.map((a, i) => (
                        <div key={`a${i}`} className="flex items-start gap-2 text-xs text-slate-700 dark:text-slate-300">
                          <svg className="h-4 w-4 text-emerald-500 shrink-0 mt-0.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M9 12l2 2 4-4M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0z" />
                          </svg>
                          {a}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <p className="text-xs text-slate-400 px-4 py-2">AI insights available — click to expand.</p>
            )}
          </div>

          {/* Comments */}
          <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200/80 dark:border-slate-800 p-4">
            <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-3">
              Comments
              {comments.length > 0 && (
                <span className="ml-1.5 text-xs font-normal text-slate-400">({comments.length})</span>
              )}
            </h2>

            <div className="flex flex-col gap-2 mb-4">
              {commentsQuery.isLoading ? (
                [1, 2].map((i) => <Sk key={i} className="h-16 rounded-lg" />)
              ) : comments.length === 0 ? (
                <p className="text-xs text-slate-400 italic">No comments yet.</p>
              ) : (
                comments
                  .filter((c) => isAgent || !c.is_internal)
                  .map((c) => <CommentItem key={c.id} comment={c} />)
              )}
            </div>

            {/* Add comment */}
            <div className="border-t border-slate-100 dark:border-slate-800 pt-3 flex flex-col gap-2">
              <textarea
                className="input resize-none text-sm"
                rows={3}
                placeholder="Write a comment…"
                value={commentText}
                onChange={(e) => setCommentText(e.target.value)}
              />
              <div className="flex items-center justify-between">
                {isAgent && (
                  <label className="flex items-center gap-2 cursor-pointer select-none text-xs text-slate-500 dark:text-slate-400">
                    <input
                      type="checkbox"
                      className="rounded border-slate-300 text-amber-500 focus:ring-amber-400"
                      checked={isInternal}
                      onChange={(e) => setIsInternal(e.target.checked)}
                    />
                    Internal note
                  </label>
                )}
                <div className="ml-auto">
                  <Button
                    disabled={!commentText.trim() || commentMutation.isPending}
                    onClick={() => commentMutation.mutate()}
                  >
                    {commentMutation.isPending ? 'Posting…' : 'Post'}
                  </Button>
                </div>
              </div>
              {commentMutation.isError && (
                <p className="text-xs text-red-600">Failed to post comment.</p>
              )}
            </div>
          </div>

          {/* Audit trail */}
          {isAgent && (
            <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200/80 dark:border-slate-800 overflow-hidden">
              <div className="px-4 py-3 border-b border-slate-100 dark:border-slate-800">
                <span className="text-sm font-semibold text-slate-700 dark:text-slate-300">Audit Trail</span>
              </div>
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-slate-100 dark:border-slate-800">
                    <th className="text-left px-4 py-2 text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Time</th>
                    <th className="text-left px-4 py-2 text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Actor</th>
                    <th className="text-left px-4 py-2 text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Action</th>
                    <th className="px-4 py-2 w-8" />
                  </tr>
                </thead>
                <tbody>
                  {auditQuery.isLoading ? (
                    <tr>
                      <td colSpan={4} className="px-4 py-4 text-center text-xs text-slate-400">Loading…</td>
                    </tr>
                  ) : auditQuery.data?.items.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="px-4 py-4 text-center text-xs text-slate-400">No audit entries</td>
                    </tr>
                  ) : (
                    (auditQuery.data?.items ?? []).map((entry) => (
                      <AuditRow key={entry.id} entry={entry} />
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* ── Right column ─────────────────────────────────────────────── */}
        <div className="flex flex-col gap-4">

          {/* Ticket info */}
          <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200/80 dark:border-slate-800 p-4">
            <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-2">Ticket Info</h2>
            <div className="flex flex-col">
              <MetaRow label="Reporter"  value={ticket.reporter_id} mono />
              <MetaRow label="Assignee"  value={ticket.assignee_id ?? 'Unassigned'} mono={!!ticket.assignee_id} />
              <MetaRow label="Department" value={ticket.department} />
              <MetaRow label="Source"    value={<span className="capitalize">{ticket.source}</span>} />
              <MetaRow label="Category"  value={ticket.category_id} mono={!!ticket.category_id} />
              <MetaRow label="Created"   value={fmtDate(ticket.created_at)} />
              <MetaRow label="Updated"   value={fmtDate(ticket.updated_at)} />
              {ticket.first_response_at && <MetaRow label="1st Response" value={fmtDate(ticket.first_response_at)} />}
              {ticket.resolved_at       && <MetaRow label="Resolved At"  value={fmtDate(ticket.resolved_at)} />}
            </div>
          </div>

          {/* SLA + controls */}
          <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200/80 dark:border-slate-800 p-4">
            <div className="flex items-center justify-between mb-2">
              <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300">SLA</h2>
              {isAgent && (
                <button
                  className="text-xs text-brand-600 dark:text-brand-400 hover:underline"
                  disabled={pauseSLAMutation.isPending || resumeSLAMutation.isPending}
                  onClick={() => ticket.sla_paused_at ? resumeSLAMutation.mutate() : pauseSLAMutation.mutate()}
                >
                  {ticket.sla_paused_at ? 'Resume' : 'Pause'} SLA
                </button>
              )}
            </div>
            <div className="flex flex-col">
              <MetaRow label="Status"      value={<SLABadge breached={ticket.sla_breached} dueAt={ticket.resolution_due_at} />} />
              <MetaRow label="Response Due"   value={<span className={cn('text-xs', ticket.sla_breached ? 'text-red-600 font-medium' : '')}>{fmtDate(ticket.response_due_at)}</span>} />
              <MetaRow label="Resolution Due" value={<span className={cn('text-xs', ticket.sla_breached ? 'text-red-600 font-medium' : '')}>{fmtDate(ticket.resolution_due_at)}</span>} />
            </div>
          </div>

          {/* Tags + Sentiment combined */}
          {(ticket.tags.length > 0 || ticket.ai_sentiment) && (
            <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200/80 dark:border-slate-800 p-4">
              {ticket.tags.length > 0 && (
                <div className={cn(ticket.ai_sentiment ? 'mb-3 pb-3 border-b border-slate-100 dark:border-slate-800' : '')}>
                  <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-2">Tags</h2>
                  <div className="flex flex-wrap gap-1.5">
                    {ticket.tags.map((tag) => (
                      <span key={tag} className="pill bg-brand-50 text-brand-700 dark:bg-brand-900/30 dark:text-brand-300">
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {ticket.ai_sentiment && (
                <div>
                  <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-1.5">Sentiment</h2>
                  <span className={cn('pill text-xs',
                    ticket.ai_sentiment === 'positive' ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400' :
                    ticket.ai_sentiment === 'negative' ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400' :
                    'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400'
                  )}>
                    {ticket.ai_sentiment}
                  </span>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
