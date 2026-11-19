import { api, AI_TIMEOUT_MS } from '@/lib/api';

export type VersionStatus = 'pending' | 'processing' | 'ready' | 'failed';

/**
 * Confidence band, computed by the backend and sent as a label.
 *
 * Deliberately not derived here from `confidence`. The ticket AI badge does
 * derive its own bands and has drifted from the backend's thresholds — a
 * ticket scored 0.35 reads "Med Risk" on the badge and "Low Risk" in every
 * backend list. One owner for a threshold, and it is the server.
 */
export type ConfidenceBand = 'high' | 'medium' | 'low';

export interface KBCollection {
  id: string;
  name: string;
  description: string | null;
  is_active: boolean;
  /** Roles allowed to retrieve from this collection. Empty means nobody. */
  granted_roles: string[];
  document_count: number;
  created_at: string;
}

export interface KBVersion {
  id: string;
  version_no: number;
  status: VersionStatus;
  error_message: string | null;
  chunk_count: number;
  embedded_count: number;
  page_count: number | null;
  size_bytes: number;
  embedding_model: string | null;
  is_active: boolean;
  created_at: string;
}

export interface KBDocument {
  id: string;
  collection_id: string;
  title: string;
  original_filename: string;
  content_type: string;
  status: VersionStatus;
  chunk_count: number;
  page_count: number | null;
  size_bytes: number;
  active_version_no: number | null;
  version_count: number;
  versions: KBVersion[];
  created_at: string;
  updated_at: string;
  was_duplicate?: boolean;
}

export interface KBSource {
  chunk_id: string;
  document_id: string;
  document_title: string;
  heading_path: string | null;
  page_from: number | null;
  page_to: number | null;
  similarity: number | null;
  /** True when the answer actually cited this passage, not merely retrieved it. */
  cited: boolean;
  /** The [n] marker this passage was given in the prompt. */
  marker: number;
  excerpt: string;
}

export interface KBAnswer {
  question: string;
  answer: string | null;
  abstained: boolean;
  abstain_reason: string | null;
  confidence: number;
  confidence_band: ConfidenceBand;
  sources: KBSource[];
  rejected_citations: number[];
  error: string | null;
  timing: { retrieval_ms: number; total_ms: number };
}

export interface KBStatus {
  enabled: boolean;
  embedding_model: string;
  embedding_dim: number;
  accessible_collections: number;
  indexed_chunks: number;
  versions_in_progress: number;
  versions_failed: number;
  can_manage: boolean;
}

export async function getKbStatus(): Promise<KBStatus> {
  const { data } = await api.get('/kb/status');
  return data.data;
}

export async function listCollections(): Promise<KBCollection[]> {
  const { data } = await api.get('/kb/collections');
  return data.data;
}

export async function createCollection(body: {
  name: string;
  description?: string;
}): Promise<KBCollection> {
  const { data } = await api.post('/kb/collections', body);
  return data.data;
}

export async function updateCollection(
  id: string,
  body: { name?: string; description?: string; is_active?: boolean },
): Promise<KBCollection> {
  const { data } = await api.patch(`/kb/collections/${id}`, body);
  return data.data;
}

export async function setGrants(id: string, roles: string[]): Promise<KBCollection> {
  const { data } = await api.put(`/kb/collections/${id}/grants`, { roles });
  return data.data;
}

export async function deleteCollection(id: string): Promise<void> {
  await api.delete(`/kb/collections/${id}`);
}

export async function listDocuments(collectionId: string): Promise<KBDocument[]> {
  const { data } = await api.get(`/kb/collections/${collectionId}/documents`);
  return data.data;
}

/**
 * Upload a document, or a new version of one.
 *
 * Uses the AI timeout, not the 15s default: ingestion parses, chunks and
 * embeds inside the request, and a 200-page PDF against a local embedding
 * model takes minutes. The default would abort a request the server is still
 * happily working on, and the user would see a failure while the document
 * quietly finished indexing.
 */
export async function uploadDocument(
  collectionId: string,
  file: File,
  opts: { title?: string; documentId?: string } = {},
): Promise<KBDocument> {
  const form = new FormData();
  form.append('file', file);
  if (opts.title) form.append('title', opts.title);
  if (opts.documentId) form.append('document_id', opts.documentId);

  const { data } = await api.post(`/kb/collections/${collectionId}/documents`, form, {
    timeout: AI_TIMEOUT_MS,
  });
  return data.data;
}

export async function reindexDocument(documentId: string): Promise<KBDocument> {
  const { data } = await api.post(`/kb/documents/${documentId}/reindex`, null, {
    timeout: AI_TIMEOUT_MS,
  });
  return data.data;
}

export async function deleteDocument(documentId: string): Promise<void> {
  await api.delete(`/kb/documents/${documentId}`);
}

export async function downloadDocument(doc: KBDocument): Promise<void> {
  const resp = await api.get(`/kb/documents/${doc.id}/download`, { responseType: 'blob' });
  const url = URL.createObjectURL(resp.data as Blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = doc.original_filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export async function askKnowledgeBase(question: string): Promise<KBAnswer> {
  const { data } = await api.post('/kb/query', { question }, { timeout: AI_TIMEOUT_MS });
  return data.data;
}

/**
 * Why the system declined to answer, in the user's terms.
 *
 * Every branch says what to do next. "No answer" with no explanation reads as
 * a broken feature; "nothing in the documents you can see covers this" reads
 * as a working one that was honest.
 */
export function abstainMessage(reason: string | null): string {
  switch (reason) {
    case 'no_passages':
      return 'Nothing in the documents available to you covers this. Try different wording, or ask an administrator whether the relevant document has been uploaded.';
    case 'model_insufficient_context':
      return 'The documents that matched do not actually answer this question. Rephrasing with the exact term used in the policy often helps.';
    case 'no_valid_citations':
      return 'A draft answer was produced but none of it could be traced back to a real passage, so it was discarded rather than shown.';
    case 'low_confidence':
      return 'The supporting passages were too weak to answer safely. Treat anything below as unverified and check the source document directly.';
    case 'model_unavailable':
      return 'The local AI model could not be reached, so no answer could be generated. Retrieval itself is fine — try again shortly.';
    case 'kb_disabled':
      return 'The knowledge base is switched off in this environment.';
    default:
      return 'No grounded answer could be produced for this question.';
  }
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}
