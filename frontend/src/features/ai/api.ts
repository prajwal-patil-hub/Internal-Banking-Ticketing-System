import { api } from '@/lib/api';

export interface ChatMessage {
  id: string;
  session_id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  tokens_used: number | null;
  latency_ms: number | null;
  created_at: string;
}

export interface ChatSession {
  id: string;
  title: string | null;
  context_type: string | null;
  context_id: string | null;
  is_active: boolean;
  created_at: string;
}

export interface SendMessagePayload {
  message: string;
  session_id?: string;
  context_type?: string;
  context_id?: string;
}

export interface SendMessageResponse {
  session_id: string;
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
  const { data } = await api.post('/ai/chat', payload);
  return data.data;
}

export async function getChatSessions(): Promise<ChatSession[]> {
  const { data } = await api.get('/ai/sessions');
  return data.data?.items ?? data.data ?? [];
}

export async function getChatSession(sessionId: string): Promise<{ session: ChatSession; messages: ChatMessage[] }> {
  const { data } = await api.get(`/ai/sessions/${sessionId}`);
  return data.data;
}

export async function endChatSession(sessionId: string): Promise<void> {
  await api.delete(`/ai/sessions/${sessionId}`);
}

export async function categorizeText(text: string, title?: string): Promise<CategorizeResponse> {
  const { data } = await api.post('/ai/categorize', { text, title });
  return data.data;
}

export async function extractEmail(raw_email: string): Promise<ExtractEmailResponse> {
  const { data } = await api.post('/ai/extract-email', { raw_email });
  return data.data;
}
