import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Card } from '@/components/Card';
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
} from '@/features/tickets/api';
import type { Ticket, Comment, TicketStatus } from '@/features/tickets/api';
import { getAuditLog } from '@/features/tickets/api';

const STALE = 30_000;

// Status FSM transitions
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

const STATUS_TRANSITION_LABELS: Record<TicketStatus, string> = {
  new:          'Mark New',
  acknowledged: 'Acknowledge',
  assigned:     'Assign',
  in_progress:  'Start Work',
  on_hold:      'Put On Hold',
  escalated:    'Escalate',
  resolved:     'Mark Resolved',
  closed:       'Close',
  reopened:     'Reopen',
};

const STATUS_TRANSITION_VARIANTS: Partial<Record<TicketStatus, 'primary' | 'ghost' | 'danger'>> = {
  escalated: 'danger',
  closed:    'ghost',
  resolved:  'primary',
};

// ---------- Skeleton ----------

function Skeleton({ className }: { className?: string }) {
  return <div className={cn('animate-pulse rounded-xl bg-slate-200 dark:bg-slate-800', className)} />;
}

function DetailSkeleton() {
  return (
    <div className="flex flex-col gap-6">
      <Skeleton className="h-8 w-72" />
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <div className="xl:col-span-2 flex flex-col gap-4">
          <Skeleton className="h-48" />
          <Skeleton className="h-40" />
        </div>
        <div className="flex flex-col gap-4">
          <Skeleton className="h-32" />
          <Skeleton className="h-32" />
        </div>
      </div>
    </div>
  );
}

// ---------- Metadata row ----------

function MetaItem({ label, value, mono = false }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs text-slate-500 uppercase tracking-wide font-medium">{label}</span>
      <span className={cn('text-sm text-slate-800 dark:text-slate-200', mono && 'font-mono')}>{value ?? '—'}</span>
    </div>
  );
}

// ---------- Comment item ----------

function CommentItem({ comment, isInternal }: { comment: Comment; isInternal?: boolean }) {
  const date = new Date(comment.created_at);
  const timeStr = date.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }) +
    ' ' + date.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });

  return (
    <div className={cn(
      'flex flex-col gap-1.5 p-4 rounded-xl border',
      isInternal
        ? 'bg-amber-50 border-amber-200 dark:bg-amber-900/10 dark:border-amber-800/40'
        : 'bg-white border-slate-100 dark:bg-slate-800 dark:border-slate-700',
    )}>
      <div className="flex items-center gap-2">
        <div className="h-7 w-7 rounded-full bg-brand-100 dark:bg-brand-900/40 flex items-center justify-center text-brand-700 dark:text-brand-300 text-xs font-semibold shrink-0">
          {comment.author_id?.slice(0, 2).toUpperCase() ?? 'SY'}
        </div>
        <span className="text-xs font-medium text-slate-700 dark:text-slate-300">
          {comment.author_id ? `Agent #${comment.author_id.slice(0, 6)}` : 'System'}
        </span>
        {comment.is_internal && (
          <Badge tone="warning" className="text-[10px] py-0.5">Internal Note</Badge>
        )}
        {comment.ai_generated && (
          <Badge tone="info" className="text-[10px] py-0.5">AI Generated</Badge>
        )}
        <span className="text-xs text-slate-400 ml-auto">{timeStr}</span>
      </div>
      <p className="text-sm text-slate-700 dark:text-slate-300 whitespace-pre-wrap leading-relaxed">
        {comment.body}
      </p>
    </div>
  );
}

// ---------- Audit row ----------

function AuditRow({ entry }: { entry: { id: string; action: string; actor_email: string | null; entity_type: string; created_at: string; old_values: Record<string, unknown> | null; new_values: Record<string, unknown> | null } }) {
  const [expanded, setExpanded] = useState(false);
  const date = new Date(entry.created_at);
  const timeStr = date.toLocaleDateString('en-GB', { day: '2-digit', month: 'short' }) +
    ' ' + date.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });

  const actionClass: Record<string, string> = {
    create: 'bg-emerald-100 text-emerald-700',
    update: 'bg-blue-100 text-blue-700',
    delete: 'bg-red-100 text-red-700',
    status_change: 'bg-purple-100 text-purple-700',
    assign: 'bg-indigo-100 text-indigo-700',
  };

  const cls = actionClass[entry.action] ?? 'bg-slate-100 text-slate-700';

  return (
    <>
      <tr
        className="border-b border-slate-50 dark:border-slate-800 hover:bg-surface-subtle dark:hover:bg-slate-800/30 cursor-pointer transition-colors"
        onClick={() => setExpanded((p) => !p)}
      >
        <td className="px-4 py-2.5 text-xs text-slate-500 whitespace-nowrap">{timeStr}</td>
        <td className="px-4 py-2.5 text-xs font-medium text-slate-700 dark:text-slate-300">{entry.actor_email ?? 'System'}</td>
        <td className="px-4 py-2.5">
          <span className={cn('pill text-xs', cls)}>{entry.action}</span>
        </td>
        <td className="px-4 py-2.5 text-xs text-slate-500">{entry.entity_type}</td>
        <td className="px-4 py-2.5 text-right">
          {(entry.old_values || entry.new_values) && (
            <svg className={cn('h-3.5 w-3.5 text-slate-400 inline-block transition-transform', expanded && 'rotate-180')} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M6 9l6 6 6-6" />
            </svg>
          )}
        </td>
      </tr>
      {expanded && (entry.old_values || entry.new_values) && (
        <tr className="bg-slate-50 dark:bg-slate-900/50">
          <td colSpan={5} className="px-4 py-3">
            <div className="grid grid-cols-2 gap-3 text-xs">
              {entry.old_values && (
                <div>
                  <p className="font-medium text-slate-500 mb-1">Before</p>
                  <pre className="bg-white dark:bg-slate-800 rounded-lg p-2 overflow-x-auto text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-700">
                    {JSON.stringify(entry.old_values, null, 2)}
                  </pre>
                </div>
              )}
              {entry.new_values && (
                <div>
                  <p className="font-medium text-slate-500 mb-1">After</p>
                  <pre className="bg-white dark:bg-slate-800 rounded-lg p-2 overflow-x-auto text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-700">
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

// ---------- Main Page ----------

export function TicketDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const queryClient = useQueryClient();

  const [commentText, setCommentText] = useState('');
  const [isInternalNote, setIsInternalNote] = useState(false);
  const [showAISuggestions, setShowAISuggestions] = useState(false);
  const [aiSummaryResult, setAISummaryResult] = useState<{
    summary: string;
    sentiment: string;
    risk_score: number;
  } | null>(null);
  const [aiSuggestResult, setAISuggestResult] = useState<{
    suggestions: string[];
    next_actions: string[];
  } | null>(null);

  const isAgent = ['admin', 'agent', 'supervisor', 'auditor'].includes(user?.role ?? '');

  const ticketQuery = useQuery({
    queryKey: ['tickets', id],
    queryFn: () => getTicket(id!),
    enabled: !!id,
    staleTime: STALE,
  });

  const commentsQuery = useQuery({
    queryKey: ['tickets', id, 'comments', isAgent],
    queryFn: () => getComments(id!, isAgent),
    enabled: !!id,
    staleTime: STALE,
  });

  const auditQuery = useQuery({
    queryKey: ['audit', 'ticket', id],
    queryFn: () => getAuditLog({ entity_type: 'ticket', page: 1, page_size: 10 }),
    enabled: !!id && isAgent,
    staleTime: STALE,
  });

  const statusMutation = useMutation({
    mutationFn: ({ status, comment }: { status: TicketStatus; comment?: string }) =>
      updateTicketStatus(id!, status, comment),
    onSuccess: (updated) => {
      queryClient.setQueryData(['tickets', id], updated);
    },
  });

  const commentMutation = useMutation({
    mutationFn: () => addComment(id!, commentText, isInternalNote),
    onSuccess: () => {
      setCommentText('');
      queryClient.invalidateQueries({ queryKey: ['tickets', id, 'comments'] });
    },
  });

  const summarizeMutation = useMutation({
    mutationFn: () => aiSummarize(id!),
    onSuccess: (result) => setAISummaryResult(result),
  });

  const suggestMutation = useMutation({
    mutationFn: () => aiSuggest(id!),
    onSuccess: (result) => {
      setAISuggestResult(result);
      setShowAISuggestions(true);
    },
  });

  const pauseSLAMutation = useMutation({
    mutationFn: () => pauseSLA(id!),
    onSuccess: (updated) => queryClient.setQueryData(['tickets', id], updated),
  });

  const resumeSLAMutation = useMutation({
    mutationFn: () => resumeSLA(id!),
    onSuccess: (updated) => queryClient.setQueryData(['tickets', id], updated),
  });

  if (ticketQuery.isLoading) return <DetailSkeleton />;

  if (ticketQuery.isError || !ticketQuery.data) {
    return (
      <Card className="flex flex-col items-center gap-3 py-12 text-center">
        <svg className="h-12 w-12 text-red-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10" />
          <path d="M12 8v4M12 16h.01" />
        </svg>
        <p className="text-base font-medium">Ticket not found</p>
        <p className="text-sm text-slate-500">The ticket you're looking for doesn't exist or you don't have access.</p>
        <Button variant="ghost" onClick={() => navigate('/tickets')}>Back to Tickets</Button>
      </Card>
    );
  }

  const ticket: Ticket = ticketQuery.data;
  const comments: Comment[] = commentsQuery.data ?? [];
  const availableTransitions = STATUS_TRANSITIONS[ticket.status] ?? [];

  function formatDate(d: string | null): string {
    if (!d) return '—';
    return new Date(d).toLocaleDateString('en-GB', {
      day: '2-digit', month: 'short', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  }

  return (
    <div className="flex flex-col gap-6">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm">
        <button onClick={() => navigate('/tickets')} className="text-brand-600 hover:underline dark:text-brand-400">
          Tickets
        </button>
        <span className="text-slate-400">/</span>
        <span className="font-mono text-slate-600 dark:text-slate-400">{ticket.ticket_number}</span>
      </div>

      {/* Title row */}
      <div className="flex items-start gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-2">
            <span className="font-mono text-sm font-semibold text-brand-600 bg-brand-50 dark:bg-brand-900/20 dark:text-brand-300 px-2.5 py-1 rounded-lg">
              {ticket.ticket_number}
            </span>
            <StatusBadge status={ticket.status} />
            <PriorityBadge priority={ticket.priority} />
            <SLABadge breached={ticket.sla_breached} dueAt={ticket.resolution_due_at} />
            {(ticket.ai_category || ticket.ai_risk_score !== null) && (
              <AIBadge
                category={ticket.ai_category}
                confidence={ticket.ai_confidence}
                riskScore={ticket.ai_risk_score}
              />
            )}
          </div>
          <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-100 leading-snug">
            {ticket.title}
          </h1>
        </div>

        {/* Action buttons */}
        {isAgent && (
          <div className="flex items-center gap-2 flex-wrap shrink-0">
            {availableTransitions.map((nextStatus) => (
              <Button
                key={nextStatus}
                variant={STATUS_TRANSITION_VARIANTS[nextStatus] ?? 'ghost'}
                disabled={statusMutation.isPending}
                onClick={() => statusMutation.mutate({ status: nextStatus })}
              >
                {STATUS_TRANSITION_LABELS[nextStatus]}
              </Button>
            ))}
          </div>
        )}
      </div>

      {/* Main grid */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        {/* Left column: description, AI, comments */}
        <div className="xl:col-span-2 flex flex-col gap-6">

          {/* Description */}
          <Card>
            <h2 className="text-base font-semibold mb-3">Description</h2>
            <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed whitespace-pre-wrap">
              {ticket.description}
            </p>
            {ticket.email_from && (
              <div className="mt-3 pt-3 border-t border-slate-100 dark:border-slate-800">
                <span className="text-xs text-slate-500">From email: </span>
                <span className="text-xs font-mono text-slate-700 dark:text-slate-300">{ticket.email_from}</span>
              </div>
            )}
          </Card>

          {/* AI Section */}
          <Card>
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <div className="h-7 w-7 rounded-lg bg-accent-100 dark:bg-accent-500/20 flex items-center justify-center">
                  <svg className="h-4 w-4 text-accent-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12 2a10 10 0 0 1 0 20M12 2a10 10 0 0 0 0 20M12 8v4M12 16h.01" />
                  </svg>
                </div>
                <h2 className="text-base font-semibold">AI Insights</h2>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  variant="ghost"
                  disabled={summarizeMutation.isPending}
                  onClick={() => summarizeMutation.mutate()}
                >
                  {summarizeMutation.isPending ? 'Summarizing…' : 'Generate Summary'}
                </Button>
                <Button
                  variant="ghost"
                  disabled={suggestMutation.isPending}
                  onClick={() => suggestMutation.mutate()}
                >
                  {suggestMutation.isPending ? 'Analyzing…' : 'Get Suggestions'}
                </Button>
              </div>
            </div>

            {/* Existing AI data */}
            {ticket.ai_summary && !aiSummaryResult && (
              <div className="mb-4 p-3 rounded-xl bg-surface-subtle dark:bg-slate-800">
                <p className="text-xs font-medium text-slate-500 mb-1">AI Summary</p>
                <p className="text-sm text-slate-700 dark:text-slate-300">{ticket.ai_summary}</p>
              </div>
            )}

            {/* Freshly generated summary */}
            {aiSummaryResult && (
              <div className="mb-4 p-3 rounded-xl bg-accent-50 dark:bg-accent-500/10 border border-accent-200 dark:border-accent-500/20">
                <div className="flex items-center gap-2 mb-1.5">
                  <p className="text-xs font-medium text-accent-700 dark:text-accent-400">AI Summary</p>
                  <span className={cn('pill text-[10px]',
                    aiSummaryResult.sentiment === 'positive' ? 'bg-emerald-100 text-emerald-700' :
                    aiSummaryResult.sentiment === 'negative' ? 'bg-red-100 text-red-700' :
                    'bg-slate-100 text-slate-600'
                  )}>
                    {aiSummaryResult.sentiment}
                  </span>
                  <span className={cn('pill text-[10px]',
                    aiSummaryResult.risk_score >= 0.7 ? 'bg-red-100 text-red-700' :
                    aiSummaryResult.risk_score >= 0.3 ? 'bg-amber-100 text-amber-700' :
                    'bg-emerald-100 text-emerald-700'
                  )}>
                    Risk: {(aiSummaryResult.risk_score * 100).toFixed(0)}%
                  </span>
                </div>
                <p className="text-sm text-slate-700 dark:text-slate-300">{aiSummaryResult.summary}</p>
              </div>
            )}

            {/* AI Suggestions */}
            {aiSuggestResult && showAISuggestions && (
              <div className="mt-2">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-xs font-medium text-slate-500">AI Suggestions</p>
                  <button
                    onClick={() => setShowAISuggestions(false)}
                    className="text-xs text-slate-400 hover:text-slate-600"
                  >
                    Collapse
                  </button>
                </div>
                {aiSuggestResult.suggestions.length > 0 && (
                  <div className="mb-3">
                    <p className="text-xs font-medium text-slate-600 dark:text-slate-400 mb-1.5">Suggestions</p>
                    <ul className="space-y-1">
                      {aiSuggestResult.suggestions.map((s, i) => (
                        <li key={i} className="flex items-start gap-2 text-sm text-slate-700 dark:text-slate-300">
                          <span className="h-4 w-4 rounded-full bg-brand-100 text-brand-700 flex items-center justify-center text-[10px] font-bold shrink-0 mt-0.5">{i + 1}</span>
                          {s}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {aiSuggestResult.next_actions.length > 0 && (
                  <div>
                    <p className="text-xs font-medium text-slate-600 dark:text-slate-400 mb-1.5">Next Actions</p>
                    <ul className="space-y-1">
                      {aiSuggestResult.next_actions.map((a, i) => (
                        <li key={i} className="flex items-start gap-2 text-sm text-slate-700 dark:text-slate-300">
                          <svg className="h-4 w-4 text-emerald-500 shrink-0 mt-0.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M9 12l2 2 4-4M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0z" />
                          </svg>
                          {a}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}

            {!ticket.ai_summary && !aiSummaryResult && !aiSuggestResult && (
              <p className="text-sm text-slate-400 italic">
                Click "Generate Summary" or "Get Suggestions" to run AI analysis on this ticket.
              </p>
            )}
          </Card>

          {/* Comments */}
          <Card>
            <h2 className="text-base font-semibold mb-4">
              Comments ({comments.length})
            </h2>

            <div className="flex flex-col gap-3 mb-6">
              {commentsQuery.isLoading ? (
                <div className="flex flex-col gap-3">
                  {[1, 2].map((i) => (
                    <div key={i} className="h-20 rounded-xl bg-slate-100 dark:bg-slate-800 animate-pulse" />
                  ))}
                </div>
              ) : comments.length === 0 ? (
                <p className="text-sm text-slate-400 italic">No comments yet.</p>
              ) : (
                comments
                  .filter((c) => isAgent || !c.is_internal)
                  .map((c) => (
                    <CommentItem key={c.id} comment={c} isInternal={c.is_internal} />
                  ))
              )}
            </div>

            {/* Add comment form */}
            <div className="border-t border-slate-100 dark:border-slate-800 pt-4">
              <div className="flex flex-col gap-3">
                <textarea
                  className="input resize-none"
                  rows={4}
                  placeholder="Write a comment…"
                  value={commentText}
                  onChange={(e) => setCommentText(e.target.value)}
                />
                <div className="flex items-center justify-between">
                  {isAgent && (
                    <label className="flex items-center gap-2 cursor-pointer select-none text-sm text-slate-600 dark:text-slate-400">
                      <input
                        type="checkbox"
                        className="rounded border-slate-300 text-amber-500 focus:ring-amber-400"
                        checked={isInternalNote}
                        onChange={(e) => setIsInternalNote(e.target.checked)}
                      />
                      Internal note (not visible to reporter)
                    </label>
                  )}
                  <div className="ml-auto">
                    <Button
                      disabled={!commentText.trim() || commentMutation.isPending}
                      onClick={() => commentMutation.mutate()}
                    >
                      {commentMutation.isPending ? 'Posting…' : 'Post Comment'}
                    </Button>
                  </div>
                </div>
                {commentMutation.isError && (
                  <p className="text-xs text-red-600">Failed to post comment. Please try again.</p>
                )}
              </div>
            </div>
          </Card>

          {/* Audit Trail */}
          {isAgent && (
            <Card padded={false}>
              <div className="p-6 pb-2">
                <h2 className="text-base font-semibold">Audit Trail</h2>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-100 dark:border-slate-800">
                      <th className="text-left px-4 py-2 text-xs uppercase tracking-wide text-slate-500 font-medium">Time</th>
                      <th className="text-left px-4 py-2 text-xs uppercase tracking-wide text-slate-500 font-medium">Actor</th>
                      <th className="text-left px-4 py-2 text-xs uppercase tracking-wide text-slate-500 font-medium">Action</th>
                      <th className="text-left px-4 py-2 text-xs uppercase tracking-wide text-slate-500 font-medium">Entity</th>
                      <th className="px-4 py-2" />
                    </tr>
                  </thead>
                  <tbody>
                    {auditQuery.isLoading ? (
                      <tr>
                        <td colSpan={5} className="px-4 py-6 text-center text-sm text-slate-400">Loading audit trail…</td>
                      </tr>
                    ) : auditQuery.data?.items.length === 0 ? (
                      <tr>
                        <td colSpan={5} className="px-4 py-6 text-center text-sm text-slate-400">No audit entries</td>
                      </tr>
                    ) : (
                      (auditQuery.data?.items ?? []).map((entry) => (
                        <AuditRow key={entry.id} entry={entry} />
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </div>

        {/* Right column: metadata, SLA, tags */}
        <div className="flex flex-col gap-6">
          {/* Ticket Info */}
          <Card>
            <h2 className="text-base font-semibold mb-4">Ticket Info</h2>
            <div className="grid grid-cols-1 gap-3">
              <MetaItem label="Reporter" value={ticket.reporter_id} mono />
              <MetaItem label="Assignee" value={ticket.assignee_id ?? 'Unassigned'} mono={!!ticket.assignee_id} />
              <MetaItem label="Department" value={ticket.department} />
              <MetaItem label="Source" value={<span className="capitalize">{ticket.source}</span>} />
              <MetaItem label="Category" value={ticket.category_id} mono={!!ticket.category_id} />
              <MetaItem label="Created" value={formatDate(ticket.created_at)} />
              <MetaItem label="Updated" value={formatDate(ticket.updated_at)} />
              {ticket.first_response_at && (
                <MetaItem label="First Response" value={formatDate(ticket.first_response_at)} />
              )}
              {ticket.resolved_at && (
                <MetaItem label="Resolved At" value={formatDate(ticket.resolved_at)} />
              )}
            </div>
          </Card>

          {/* SLA Details */}
          <Card>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-base font-semibold">SLA Details</h2>
              {isAgent && (
                <Button
                  variant="ghost"
                  disabled={pauseSLAMutation.isPending || resumeSLAMutation.isPending}
                  onClick={() => ticket.sla_breached ? resumeSLAMutation.mutate() : pauseSLAMutation.mutate()}
                >
                  {ticket.sla_breached ? 'Resume SLA' : 'Pause SLA'}
                </Button>
              )}
            </div>
            <div className="flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <span className="text-xs text-slate-500">Status</span>
                <SLABadge breached={ticket.sla_breached} dueAt={ticket.resolution_due_at} />
              </div>
              <div className="flex flex-col gap-0.5">
                <span className="text-xs text-slate-500 uppercase tracking-wide font-medium">Response Due</span>
                <span className={cn('text-sm', ticket.sla_breached ? 'text-red-600 font-medium' : 'text-slate-700 dark:text-slate-300')}>
                  {formatDate(ticket.response_due_at)}
                </span>
              </div>
              <div className="flex flex-col gap-0.5">
                <span className="text-xs text-slate-500 uppercase tracking-wide font-medium">Resolution Due</span>
                <span className={cn('text-sm', ticket.sla_breached ? 'text-red-600 font-medium' : 'text-slate-700 dark:text-slate-300')}>
                  {formatDate(ticket.resolution_due_at)}
                </span>
              </div>
            </div>
          </Card>

          {/* Tags */}
          {ticket.tags.length > 0 && (
            <Card>
              <h2 className="text-base font-semibold mb-3">Tags</h2>
              <div className="flex flex-wrap gap-2">
                {ticket.tags.map((tag) => (
                  <span
                    key={tag}
                    className="pill bg-brand-50 text-brand-700 dark:bg-brand-900/30 dark:text-brand-300"
                  >
                    {tag}
                  </span>
                ))}
              </div>
            </Card>
          )}

          {/* AI Sentiment */}
          {ticket.ai_sentiment && (
            <Card>
              <h2 className="text-base font-semibold mb-2">AI Sentiment</h2>
              <span className={cn('pill text-sm',
                ticket.ai_sentiment === 'positive' ? 'bg-emerald-100 text-emerald-700' :
                ticket.ai_sentiment === 'negative' ? 'bg-red-100 text-red-700' :
                'bg-slate-100 text-slate-600'
              )}>
                {ticket.ai_sentiment}
              </span>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
