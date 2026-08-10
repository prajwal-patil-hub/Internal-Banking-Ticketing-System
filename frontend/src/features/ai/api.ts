import { api, AI_TIMEOUT_MS, API_BASE_URL, refreshAccessToken } from '@/lib/api';

/** Every AI-backed request needs the long timeout — see AI_TIMEOUT_MS. */
const aiCfg = { timeout: AI_TIMEOUT_MS };

export interface ChatMessage {
  id: string;
  session_id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  input_tokens: number | null;
  output_tokens: number | null;
  created_at: string;
}

export interface ChatSession {
  id: string;
  user_id: string;
  ticket_id: string | null;
  title: string | null;
  is_active: boolean;
  ended_at: string | null;
  message_count: number;
  created_at: string;
  updated_at: string;
}

export interface AIHealth {
  enabled: boolean;
  provider: string;
  model: string;
  base_url: string;
  timeout_seconds: number;
  reachable: boolean;
  model_available: boolean;
  available_models: string[];
  error: string | null;
  hint: string | null;
}

export interface SendMessagePayload {
  message: string;
  session_id?: string;
  context_type?: string;
  context_id?: string;
}

export interface SendMessageResponse {
  session_id: string;
  /** True when the reply is a fallback explaining an AI failure, not a real completion. */
  degraded: boolean;
  user_message: ChatMessage;
  assistant_message: ChatMessage;
}

export interface CategorizeResponse {
  category: string;
  subcategory: string | null;
  confidence: number;
  priority: string;
  tags: string[];
  department: string | null;
}

export interface ExtractEmailResponse {
  subject: string;
  body: string;
  from_email: string;
  priority: string;
  category: string;
  sentiment: string;
}

export async function sendChatMessage(payload: SendMessagePayload): Promise<SendMessageResponse> {
  // Backend keys the ticket link as `context_id`; it accepts `ticket_id` too.
  const { data } = await api.post('/ai/chat', payload, aiCfg);
  return data.data;
}

export interface StreamHandlers {
  /** Fires once, as soon as the session is known — before any token. */
  onMeta?: (meta: { session_id: string }) => void;
  /** Fires per token. Append to whatever you're rendering. */
  onDelta: (text: string) => void;
  /** Fires once at the end, even when the reply was degraded. */
  onDone?: (done: {
    session_id: string;
    message_id: string | null;
    input_tokens: number;
    output_tokens: number;
    latency_ms: number;
    degraded: boolean;
  }) => void;
  /** The model failed; `message` explains how to fix it. */
  onError?: (message: string) => void;
}

/**
 * Stream a chat reply token by token over SSE.
 *
 * Uses `fetch` rather than axios: XHR buffers the whole body before resolving,
 * which would defeat streaming entirely. That means re-implementing the two
 * things the axios instance normally provides — the bearer header and the
 * single-flight 401 refresh — so both are pulled from lib/api rather than
 * copied.
 *
 * Returns the assembled reply. Pass `signal` to cancel an in-flight stream.
 */
export async function streamChatMessage(
  payload: SendMessagePayload,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<string> {
  const send = (token: string | null) =>
    fetch(`${API_BASE_URL}/ai/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(payload),
      signal,
    });

  let response = await send(localStorage.getItem('access_token'));

  if (response.status === 401) {
    const refreshed = await refreshAccessToken();
    if (!refreshed) {
      window.dispatchEvent(new CustomEvent('auth:logout'));
      throw new Error('Session expired. Please sign in again.');
    }
    response = await send(refreshed);
  }

  if (!response.ok || !response.body) {
    throw new Error(`Streaming request failed (HTTP ${response.status}).`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let assembled = '';

  // SSE frames are separated by a blank line; a chunk can split one in half,
  // so hold the remainder in `buffer` until its terminator arrives.
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let split: number;
    while ((split = buffer.indexOf('\n\n')) !== -1) {
      const frame = buffer.slice(0, split);
      buffer = buffer.slice(split + 2);

      let event = 'message';
      const dataLines: string[] = [];
      for (const line of frame.split('\n')) {
        if (line.startsWith('event:')) event = line.slice(6).trim();
        else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
      }
      if (!dataLines.length) continue;

      let parsed: Record<string, never>;
      try {
        parsed = JSON.parse(dataLines.join('\n'));
      } catch {
        continue; // ignore a malformed frame rather than killing the stream
      }

      if (event === 'delta') {
        const text = (parsed as { text?: string }).text ?? '';
        assembled += text;
        handlers.onDelta(text);
      } else if (event === 'meta') {
        handlers.onMeta?.(parsed as unknown as { session_id: string });
      } else if (event === 'done') {
        handlers.onDone?.(parsed as unknown as Parameters<NonNullable<StreamHandlers['onDone']>>[0]);
      } else if (event === 'error') {
        handlers.onError?.((parsed as { message?: string }).message ?? 'AI request failed.');
      }
    }
  }

  return assembled;
}

export async function getAIHealth(): Promise<AIHealth> {
  const { data } = await api.get('/ai/health');
  return data.data;
}

export async function getChatSessions(): Promise<ChatSession[]> {
  const { data } = await api.get('/ai/sessions');
  return data.data;
}

export async function getChatSession(
  sessionId: string,
): Promise<ChatSession & { messages: ChatMessage[] }> {
  const { data } = await api.get(`/ai/sessions/${sessionId}`);
  return data.data;
}

export async function endChatSession(sessionId: string): Promise<void> {
  await api.delete(`/ai/sessions/${sessionId}`);
}

export async function categorizeText(text: string, title?: string): Promise<CategorizeResponse> {
  const { data } = await api.post('/ai/categorize', { text, title }, aiCfg);
  return data.data;
}

export async function extractEmail(raw_email: string): Promise<ExtractEmailResponse> {
  const { data } = await api.post('/ai/extract-email', { raw_email }, aiCfg);
  return data.data;
}
