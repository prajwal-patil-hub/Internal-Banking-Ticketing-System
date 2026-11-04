import { useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { Button } from '@/components/Button';
import { cn } from '@/lib/cn';
import { extractError } from '@/lib/api';
import { useAuth } from '@/store/auth';
import { PageHeader, PageShell } from '@/components/PageHeader';
import {
  abstainMessage,
  askKnowledgeBase,
  createCollection,
  deleteCollection,
  deleteDocument,
  downloadDocument,
  formatBytes,
  getKbStatus,
  listCollections,
  listDocuments,
  reindexDocument,
  setGrants,
  uploadDocument,
  type ConfidenceBand,
  type KBAnswer,
  type KBCollection,
  type KBDocument,
  type VersionStatus,
} from '@/features/knowledge/api';

/**
 * The knowledge base: administrators curate documents, staff ask questions.
 *
 * Two things this screen is deliberate about.
 *
 * **A collection with no grants is shown as a problem, not as normal.** A new
 * collection is readable by nobody until a role is granted, which is the right
 * default but silently produces a knowledge base that answers nothing. The
 * empty state says so rather than leaving an administrator to wonder why
 * upload succeeded and retrieval returns nothing.
 *
 * **Retrieved and cited are drawn differently.** The answer panel shows every
 * passage that was retrieved, but marks which ones the answer actually cited.
 * Showing only citations hides how much was considered; showing them
 * identically implies more support than exists.
 */

const ROLE_OPTIONS = ['agent', 'supervisor', 'admin'] as const;

const STATUS_META: Record<VersionStatus, { label: string; pill: string }> = {
  ready:      { label: 'Indexed',    pill: 'pill-ok' },
  processing: { label: 'Indexing…',  pill: 'pill-warn' },
  pending:    { label: 'Queued',     pill: 'pill-warn' },
  failed:     { label: 'Failed',     pill: 'pill-err' },
};

const BAND_META: Record<ConfidenceBand, { label: string; pill: string }> = {
  high:   { label: 'High confidence',   pill: 'pill-ok' },
  medium: { label: 'Medium confidence', pill: 'pill-warn' },
  low:    { label: 'Low confidence',    pill: 'pill-err' },
};

function Sk({ className }: { className?: string }) {
  return <div className={cn('animate-pulse rounded-lg bg-[var(--inset)]', className)} />;
}

/**
 * Format a count for display without trusting it to exist.
 *
 * `data.indexed_chunks.toLocaleString()` throws if the field is absent, and a
 * throw inside render takes the whole route down to a white screen — the
 * status strip is decoration, but it would kill the documents list and the
 * ask panel with it. API version skew is exactly when this matters and
 * exactly when nobody is watching, so the numbers are read defensively.
 */
function count(n: number | undefined | null): string {
  return typeof n === 'number' ? n.toLocaleString() : '—';
}

function StatTile({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="card-sm flex flex-col gap-1">
      <span className="text-[11px] uppercase tracking-widest text-[var(--tx-3)] font-semibold">
        {label}
      </span>
      <span className="text-2xl font-semibold tabular-nums">{value}</span>
      {sub && <span className="text-xs text-[var(--tx-3)]">{sub}</span>}
    </div>
  );
}

export function KnowledgeBasePage() {
  const { user } = useAuth();
  const qc = useQueryClient();

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [banner, setBanner] = useState<{ tone: 'ok' | 'err'; text: string } | null>(null);

  const statusQuery = useQuery({ queryKey: ['kb', 'status'], queryFn: getKbStatus });
  const collectionsQuery = useQuery({ queryKey: ['kb', 'collections'], queryFn: listCollections });

  const canManage = statusQuery.data?.can_manage ?? false;
  const collections = collectionsQuery.data ?? [];
  const selected =
    collections.find((c) => c.id === selectedId) ?? collections[0] ?? null;

  const documentsQuery = useQuery({
    queryKey: ['kb', 'documents', selected?.id],
    queryFn: () => listDocuments(selected!.id),
    enabled: !!selected,
  });

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ['kb'] });
  };

  return (
    <PageShell>
      <PageHeader
        title="Knowledge Base"
        subtitle="Policies, runbooks and procedure notes that staff can ask questions against. Every answer is traced back to the passage it came from."
        actions={statusQuery.data && (
          <span className="text-xs text-[var(--tx-3)] font-mono">
            {statusQuery.data.embedding_model} · {statusQuery.data.embedding_dim}d
          </span>
        )}
      />

      {banner && (
        <div
          role="status"
          className={cn(
            'rounded-lg border px-4 py-3 text-sm flex items-start justify-between gap-4',
            banner.tone === 'ok'
              ? 'border-[var(--ok)] bg-[var(--ok-bg,transparent)] text-[var(--ok)]'
              : 'border-[var(--err)] text-[var(--err)]',
          )}
        >
          <span>{banner.text}</span>
          <button onClick={() => setBanner(null)} className="shrink-0 underline">
            Dismiss
          </button>
        </div>
      )}

      {statusQuery.data && !statusQuery.data.enabled && (
        <div className="rounded-lg border border-[var(--warn)] px-4 py-3 text-sm text-[var(--warn)]">
          The knowledge base is switched off in this environment (KB_ENABLED=false).
          Documents can be browsed but no questions can be answered.
        </div>
      )}

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {statusQuery.isLoading ? (
          <>
            <Sk className="h-20" /><Sk className="h-20" /><Sk className="h-20" /><Sk className="h-20" />
          </>
        ) : statusQuery.data ? (
          <>
            <StatTile
              label="Collections"
              value={count(statusQuery.data.accessible_collections)}
              sub={canManage ? 'you can curate these' : 'granted to your role'}
            />
            <StatTile
              label="Indexed passages"
              value={count(statusQuery.data.indexed_chunks)}
              sub="searchable right now"
            />
            <StatTile
              label="Indexing"
              value={count(statusQuery.data.versions_in_progress)}
              sub="documents still processing"
            />
            <StatTile
              label="Failed"
              value={count(statusQuery.data.versions_failed)}
              sub={statusQuery.data.versions_failed ? 'needs re-indexing' : 'none'}
            />
          </>
        ) : null}
      </section>

      <AskPanel enabled={statusQuery.data?.enabled !== false} />

      <div className="grid gap-6 lg:grid-cols-[280px_1fr] items-start">
        <CollectionList
          collections={collections}
          loading={collectionsQuery.isLoading}
          selectedId={selected?.id ?? null}
          canManage={canManage}
          onSelect={setSelectedId}
          onChanged={refresh}
          onError={(text) => setBanner({ tone: 'err', text })}
        />

        {selected ? (
          <DocumentPanel
            collection={selected}
            documents={documentsQuery.data ?? []}
            loading={documentsQuery.isLoading}
            canManage={canManage}
            onChanged={refresh}
            onNotice={setBanner}
          />
        ) : (
          <div className="card text-sm text-[var(--tx-3)]">
            {collectionsQuery.isLoading
              ? 'Loading collections…'
              : canManage
                ? 'No collections yet. Create one to start uploading documents.'
                : 'No collections have been shared with your role yet. An administrator grants access per collection.'}
          </div>
        )}
      </div>

      {user?.role === 'branch_user' && (
        <p className="text-xs text-[var(--tx-3)]">
          The knowledge base holds internal staff procedure and is not available to branch users.
        </p>
      )}
    </PageShell>
  );
}

// ---------------------------------------------------------------------------
// Ask
// ---------------------------------------------------------------------------

function AskPanel({ enabled }: { enabled: boolean }) {
  const [question, setQuestion] = useState('');
  const [result, setResult] = useState<KBAnswer | null>(null);
  const [error, setError] = useState<string | null>(null);

  const ask = useMutation({
    mutationFn: askKnowledgeBase,
    onSuccess: (data) => { setResult(data); setError(null); },
    onError: (err) => { setError(extractError(err).message); setResult(null); },
  });

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (question.trim() && enabled) ask.mutate(question.trim());
  };

  return (
    <section className="card flex flex-col gap-4">
      <div>
        <h2 className="font-semibold">Ask the knowledge base</h2>
        <p className="text-sm text-[var(--tx-3)] mt-0.5">
          Answers come only from documents your role can see, and every claim is
          linked to the passage it came from.
        </p>
      </div>

      <form onSubmit={submit} className="flex flex-col sm:flex-row gap-2">
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          disabled={!enabled}
          placeholder="How long does a customer have to raise a chargeback?"
          aria-label="Your question for the knowledge base"
          className="input flex-1"
        />
        <Button type="submit" disabled={!enabled || !question.trim() || ask.isPending}>
          {ask.isPending ? 'Searching…' : 'Ask'}
        </Button>
      </form>

      {ask.isPending && (
        <div className="flex flex-col gap-2">
          <Sk className="h-4 w-3/4" />
          <Sk className="h-4 w-1/2" />
        </div>
      )}

      {error && <p className="text-sm text-[var(--err)]">{error}</p>}

      {result && !ask.isPending && <AnswerView result={result} />}
    </section>
  );
}

function AnswerView({ result }: { result: KBAnswer }) {
  const band = BAND_META[result.confidence_band];
  const cited = result.sources.filter((s) => s.cited);
  const considered = result.sources.filter((s) => !s.cited);

  return (
    <div className="flex flex-col gap-4 border-t border-[var(--bd)] pt-4">
      {result.abstained ? (
        <div className="rounded-lg border border-[var(--warn)] px-4 py-3">
          <p className="text-sm font-medium text-[var(--warn)]">No grounded answer</p>
          <p className="text-sm text-[var(--tx-2)] mt-1">
            {abstainMessage(result.abstain_reason)}
          </p>
          {result.error && (
            <p className="text-xs text-[var(--tx-3)] mt-2 whitespace-pre-line">{result.error}</p>
          )}
        </div>
      ) : (
        <>
          <div className="flex items-center gap-2 flex-wrap">
            <span className={cn('pill text-xs', band.pill)}>{band.label}</span>
            <span className="text-xs text-[var(--tx-3)] tabular-nums">
              {Math.round(result.confidence * 100)}% · {cited.length} source
              {cited.length === 1 ? '' : 's'} cited · {result.timing.total_ms} ms
            </span>
          </div>
          <p className="text-sm leading-relaxed whitespace-pre-line">{result.answer}</p>
        </>
      )}

      {result.rejected_citations.length > 0 && (
        <p className="text-xs text-[var(--err)]">
          {result.rejected_citations.length} fabricated citation
          {result.rejected_citations.length === 1 ? '' : 's'} were removed before this was
          shown. The claims they supported were discarded, not displayed uncited.
        </p>
      )}

      {cited.length > 0 && <SourceList title="Cited sources" sources={cited} emphasise />}
      {considered.length > 0 && (
        <SourceList title="Also retrieved, not cited" sources={considered} />
      )}
    </div>
  );
}

function SourceList({
  title, sources, emphasise = false,
}: {
  title: string;
  sources: KBAnswer['sources'];
  emphasise?: boolean;
}) {
  return (
    <div className="flex flex-col gap-2">
      <h3 className="text-[11px] uppercase tracking-widest text-[var(--tx-3)] font-semibold">
        {title}
      </h3>
      <ul className="flex flex-col gap-2">
        {sources.map((s) => (
          <li
            key={s.chunk_id}
            className={cn(
              'rounded-lg border px-3 py-2 text-xs',
              emphasise ? 'border-[var(--bd)]' : 'border-dashed border-[var(--bd)] opacity-75',
            )}
          >
            <div className="flex items-baseline gap-2 flex-wrap">
              <span className="font-mono text-[var(--tx-3)]">[{s.marker}]</span>
              <span className="font-medium">{s.document_title}</span>
              {s.heading_path && (
                <span className="text-[var(--tx-3)]">· {s.heading_path}</span>
              )}
              {s.page_from && <span className="text-[var(--tx-3)]">· p.{s.page_from}</span>}
              {s.similarity !== null && (
                <span className="ml-auto tabular-nums text-[var(--tx-3)]">
                  {Math.round(s.similarity * 100)}% match
                </span>
              )}
            </div>
            <p className="mt-1 text-[var(--tx-2)] leading-relaxed">{s.excerpt}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Collections
// ---------------------------------------------------------------------------

function CollectionList({
  collections, loading, selectedId, canManage, onSelect, onChanged, onError,
}: {
  collections: KBCollection[];
  loading: boolean;
  selectedId: string | null;
  canManage: boolean;
  onSelect: (id: string) => void;
  onChanged: () => void;
  onError: (text: string) => void;
}) {
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState('');

  const create = useMutation({
    mutationFn: () => createCollection({ name: name.trim() }),
    onSuccess: () => { setName(''); setCreating(false); onChanged(); },
    onError: (err) => onError(extractError(err).message),
  });

  return (
    <aside className="card flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold text-sm">Collections</h2>
        {canManage && !creating && (
          <button
            onClick={() => setCreating(true)}
            className="text-xs underline text-[var(--tx-3)] hover:text-[var(--tx)]"
          >
            New
          </button>
        )}
      </div>

      {creating && (
        <form
          onSubmit={(e) => { e.preventDefault(); if (name.trim()) create.mutate(); }}
          className="flex flex-col gap-2"
        >
          <input
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Compliance policies"
            aria-label="New collection name"
            className="input text-sm"
          />
          <div className="flex gap-2">
            <Button type="submit" className="text-xs px-2 py-1" disabled={create.isPending}>
              {create.isPending ? 'Creating…' : 'Create'}
            </Button>
            <Button
              type="button" variant="ghost" className="text-xs px-2 py-1"
              onClick={() => { setCreating(false); setName(''); }}
            >
              Cancel
            </Button>
          </div>
        </form>
      )}

      {loading ? (
        <><Sk className="h-9" /><Sk className="h-9" /></>
      ) : collections.length === 0 ? (
        <p className="text-xs text-[var(--tx-3)]">None yet.</p>
      ) : (
        <ul className="flex flex-col gap-1">
          {collections.map((c) => (
            <li key={c.id}>
              <button
                onClick={() => onSelect(c.id)}
                className={cn(
                  'w-full text-left rounded-lg px-3 py-2 text-sm transition',
                  c.id === selectedId
                    ? 'bg-[var(--inset)] font-medium'
                    : 'hover:bg-[var(--inset)]',
                )}
              >
                <span className="flex items-center gap-2">
                  <span className="flex-1 truncate">{c.name}</span>
                  <span className="text-xs text-[var(--tx-3)] tabular-nums">
                    {c.document_count}
                  </span>
                </span>
                {/* A collection nobody can read answers nothing. Say so here
                    rather than letting an admin discover it via silence. */}
                {(c.granted_roles ?? []).length === 0 && (
                  <span className="block text-[11px] text-[var(--warn)] mt-0.5">
                    No roles granted — not searchable
                  </span>
                )}
                {!c.is_active && (
                  <span className="block text-[11px] text-[var(--tx-3)] mt-0.5">Inactive</span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}

// ---------------------------------------------------------------------------
// Documents
// ---------------------------------------------------------------------------

function DocumentPanel({
  collection, documents, loading, canManage, onChanged, onNotice,
}: {
  collection: KBCollection;
  documents: KBDocument[];
  loading: boolean;
  canManage: boolean;
  onChanged: () => void;
  onNotice: (n: { tone: 'ok' | 'err'; text: string }) => void;
}) {
  const fileRef = useRef<HTMLInputElement>(null);

  const upload = useMutation({
    mutationFn: (file: File) => uploadDocument(collection.id, file),
    onSuccess: (doc) => {
      onNotice(
        doc.was_duplicate
          ? { tone: 'ok', text: `"${doc.title}" is already indexed — nothing changed.` }
          : { tone: 'ok', text: `"${doc.title}" indexed into ${doc.chunk_count} passages.` },
      );
      onChanged();
    },
    onError: (err) => onNotice({ tone: 'err', text: extractError(err).message }),
  });

  const grants = useMutation({
    mutationFn: (roles: string[]) => setGrants(collection.id, roles),
    onSuccess: onChanged,
    onError: (err) => onNotice({ tone: 'err', text: extractError(err).message }),
  });

  const removeCollection = useMutation({
    mutationFn: () => deleteCollection(collection.id),
    onSuccess: onChanged,
    onError: (err) => onNotice({ tone: 'err', text: extractError(err).message }),
  });

  const toggleRole = (role: string) => {
    const current = collection.granted_roles ?? [];
    const next = current.includes(role)
      ? current.filter((r) => r !== role)
      : [...current, role];
    grants.mutate(next);
  };

  return (
    <section className="flex flex-col gap-4">
      <div className="card flex flex-col gap-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="font-semibold">{collection.name}</h2>
            {collection.description && (
              <p className="text-sm text-[var(--tx-3)] mt-0.5">{collection.description}</p>
            )}
          </div>
          {canManage && (
            <div className="flex gap-2">
              <input
                ref={fileRef}
                type="file"
                className="sr-only"
                accept=".pdf,.docx,.txt,.md,.csv"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) upload.mutate(file);
                  e.target.value = '';
                }}
              />
              <Button
                onClick={() => fileRef.current?.click()}
                disabled={upload.isPending}
              >
                {upload.isPending ? 'Indexing…' : 'Upload document'}
              </Button>
              <Button
                variant="danger"
                onClick={() => {
                  if (confirm(`Delete "${collection.name}" and all its documents?`)) {
                    removeCollection.mutate();
                  }
                }}
              >
                Delete
              </Button>
            </div>
          )}
        </div>

        {canManage && (
          <div className="flex flex-col gap-2 border-t border-[var(--bd)] pt-3">
            <span className="text-[11px] uppercase tracking-widest text-[var(--tx-3)] font-semibold">
              Who can search this collection
            </span>
            <div className="flex flex-wrap gap-2">
              {ROLE_OPTIONS.map((role) => {
                const on = (collection.granted_roles ?? []).includes(role);
                return (
                  <button
                    key={role}
                    onClick={() => toggleRole(role)}
                    disabled={grants.isPending}
                    aria-pressed={on}
                    className={cn(
                      'pill text-xs capitalize transition',
                      on ? 'pill-ok' : 'border border-dashed border-[var(--bd)] text-[var(--tx-3)]',
                    )}
                  >
                    {role.replace('_', ' ')}
                  </button>
                );
              })}
            </div>
            <p className="text-xs text-[var(--tx-3)]">
              Branch users and auditors cannot search the knowledge base at all, so they
              are not listed here.
            </p>
          </div>
        )}

        {upload.isPending && (
          <p className="text-xs text-[var(--tx-3)]">
            Parsing, splitting and embedding — a large PDF can take a few minutes. The
            document becomes searchable only once every passage is indexed.
          </p>
        )}
      </div>

      <div className="card flex flex-col gap-3">
        <h3 className="font-semibold text-sm">Documents</h3>
        {loading ? (
          <><Sk className="h-14" /><Sk className="h-14" /></>
        ) : documents.length === 0 ? (
          <p className="text-sm text-[var(--tx-3)]">
            No documents in this collection yet.
          </p>
        ) : (
          <ul className="flex flex-col divide-y divide-[var(--bd)]">
            {documents.map((doc) => (
              <DocumentRow
                key={doc.id}
                doc={doc}
                canManage={canManage}
                onChanged={onChanged}
                onNotice={onNotice}
              />
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

function DocumentRow({
  doc, canManage, onChanged, onNotice,
}: {
  doc: KBDocument;
  canManage: boolean;
  onChanged: () => void;
  onNotice: (n: { tone: 'ok' | 'err'; text: string }) => void;
}) {
  const meta = STATUS_META[doc.status] ?? STATUS_META.pending;
  const failed = (doc.versions ?? []).find((v) => v.status === 'failed');

  const reindex = useMutation({
    mutationFn: () => reindexDocument(doc.id),
    onSuccess: (d) => {
      onNotice({ tone: 'ok', text: `"${d.title}" re-indexed into ${d.chunk_count} passages.` });
      onChanged();
    },
    onError: (err) => onNotice({ tone: 'err', text: extractError(err).message }),
  });

  const remove = useMutation({
    mutationFn: () => deleteDocument(doc.id),
    onSuccess: onChanged,
    onError: (err) => onNotice({ tone: 'err', text: extractError(err).message }),
  });

  return (
    <li className="py-3 flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-medium text-sm truncate">{doc.title}</span>
          <span className={cn('pill text-[11px]', meta.pill)}>{meta.label}</span>
          {doc.version_count > 1 && (
            <span className="text-[11px] text-[var(--tx-3)]">
              v{doc.active_version_no ?? '—'} of {doc.version_count}
            </span>
          )}
        </div>
        <p className="text-xs text-[var(--tx-3)] mt-0.5">
          {doc.original_filename} · {formatBytes(doc.size_bytes)}
          {doc.page_count ? ` · ${doc.page_count} pages` : ''}
          {doc.status === 'ready' ? ` · ${doc.chunk_count} passages` : ''}
        </p>
        {/* The reason a failure happened is the whole value of recording it. */}
        {failed?.error_message && doc.status !== 'ready' && (
          <p className="text-xs text-[var(--err)] mt-1">{failed.error_message}</p>
        )}
      </div>

      <div className="flex gap-2 shrink-0">
        <Button
          variant="ghost"
          className="text-xs px-2 py-1"
          onClick={() => { void downloadDocument(doc); }}
        >
          Download
        </Button>
        {canManage && (
          <>
            <Button
              variant="ghost"
              className="text-xs px-2 py-1"
              disabled={reindex.isPending}
              onClick={() => reindex.mutate()}
            >
              {reindex.isPending ? 'Re-indexing…' : 'Re-index'}
            </Button>
            <Button
              variant="danger"
              className="text-xs px-2 py-1"
              onClick={() => { if (confirm(`Delete "${doc.title}"?`)) remove.mutate(); }}
            >
              Delete
            </Button>
          </>
        )}
      </div>
    </li>
  );
}
