import { api, AI_TIMEOUT_MS } from '@/lib/api';

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
