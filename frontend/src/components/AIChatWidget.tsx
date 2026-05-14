import { useState, useRef, useEffect, useCallback } from 'react';
import { useLocation } from 'react-router-dom';
import { cn } from '@/lib/cn';
import { sendChatMessage } from '@/features/ai/api';

interface DisplayMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  isTyping?: boolean;
}

export function AIChatWidget() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [sessionId, setSessionId] = useState<string | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const location = useLocation();

  // Derive ticket context from URL
  const ticketMatch = location.pathname.match(/^\/tickets\/([^/]+)$/);
  const ticketId = ticketMatch ? ticketMatch[1] : undefined;

  useEffect(() => {
    if (open) {
      setTimeout(() => textareaRef.current?.focus(), 50);
    }
  }, [open]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || sending) return;

    setInput('');
    setError(null);

    const userMsg: DisplayMessage = {
      id: `u-${Date.now()}`,
      role: 'user',
      content: text,
    };

    const typingMsg: DisplayMessage = {
      id: 'typing',
      role: 'assistant',
      content: '',
      isTyping: true,
    };

    setMessages((prev) => [...prev, userMsg, typingMsg]);
    setSending(true);

    try {
      const resp = await sendChatMessage({
        message: text,
        session_id: sessionId,
        ...(ticketId ? { context_type: 'ticket', context_id: ticketId } : {}),
      });

      setSessionId(resp.session_id);

      const assistantMsg: DisplayMessage = {
        id: resp.assistant_message.id,
        role: 'assistant',
        content: resp.assistant_message.content,
      };

      setMessages((prev) => [...prev.filter((m) => m.id !== 'typing'), assistantMsg]);
    } catch {
      setMessages((prev) => prev.filter((m) => m.id !== 'typing'));
      setError('Failed to get a response. Please try again.');
    } finally {
      setSending(false);
    }
  }, [input, sending, sessionId, ticketId]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleClose = () => {
    setOpen(false);
  };

  const handleNewSession = () => {
    setSessionId(undefined);
    setMessages([]);
    setError(null);
  };

  return (
    <>
      {/* Floating button */}
      {!open && (
        <button
          onClick={() => setOpen(true)}
          className="fixed bottom-6 right-6 z-50 h-14 w-14 rounded-full bg-brand-600 hover:bg-brand-500 text-white shadow-cardLg flex items-center justify-center transition-all duration-200 group"
          aria-label="Open AI Assistant"
        >
          {/* Pulse ring */}
          <span className="absolute inset-0 rounded-full bg-brand-500 animate-ping opacity-20 group-hover:opacity-0" />
          <svg className="h-6 w-6 relative" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 2a10 10 0 0 1 0 20" />
            <path d="M12 2a10 10 0 0 0 0 20" />
            <path d="M12 8v4M12 16h.01" />
          </svg>
        </button>
      )}

      {/* Chat panel */}
      {open && (
        <div
          className="fixed bottom-6 right-6 z-50 flex flex-col bg-white dark:bg-slate-900 rounded-2xl shadow-cardLg border border-slate-200 dark:border-slate-700"
          style={{ width: 400, height: 600 }}
        >
          {/* Header */}
          <div className="flex items-center gap-3 px-4 py-3 border-b border-slate-200 dark:border-slate-700 bg-brand-600 rounded-t-2xl">
            <div className="h-8 w-8 rounded-full bg-white/20 flex items-center justify-center shrink-0">
              <svg className="h-4 w-4 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M12 2a10 10 0 0 1 0 20M12 2a10 10 0 0 0 0 20M12 8v4M12 16h.01" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-semibold text-white leading-tight">AI Assistant</div>
              <div className="text-xs text-white/70 leading-tight">Banking AI · Powered by Claude</div>
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={handleNewSession}
                className="h-7 w-7 rounded-lg hover:bg-white/10 flex items-center justify-center text-white/80 hover:text-white transition-colors"
                title="New conversation"
              >
                <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 5v14M5 12h14" />
                </svg>
              </button>
              <button
                onClick={handleClose}
                className="h-7 w-7 rounded-lg hover:bg-white/10 flex items-center justify-center text-white/80 hover:text-white transition-colors"
                aria-label="Close"
              >
                <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M18 6 6 18M6 6l12 12" />
                </svg>
              </button>
            </div>
          </div>

          {/* Context chip */}
          {ticketId && (
            <div className="px-4 py-2 bg-brand-50 dark:bg-brand-900/20 border-b border-slate-100 dark:border-slate-800">
              <span className="text-xs text-brand-700 dark:text-brand-300 font-medium">
                Context: Ticket #{ticketId.slice(0, 8)}...
              </span>
            </div>
          )}

          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-4 py-3 flex flex-col gap-3">
            {messages.length === 0 && (
              <div className="flex flex-col items-center justify-center h-full gap-3 text-center">
                <div className="h-12 w-12 rounded-full bg-brand-100 dark:bg-brand-900/40 flex items-center justify-center">
                  <svg className="h-6 w-6 text-brand-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12 2a10 10 0 0 1 0 20M12 2a10 10 0 0 0 0 20M12 8v4M12 16h.01" />
                  </svg>
                </div>
                <div>
                  <p className="text-sm font-medium text-slate-700 dark:text-slate-300">Banking AI Assistant</p>
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 max-w-xs">
                    Ask me about tickets, SLA policies, procedures, or any banking support topic.
                  </p>
                </div>
                <div className="flex flex-col gap-1.5 w-full mt-2">
                  {['Summarize this ticket', 'What are the SLA policies?', 'Suggest resolution steps'].map((s) => (
                    <button
                      key={s}
                      onClick={() => { setInput(s); textareaRef.current?.focus(); }}
                      className="text-xs text-left px-3 py-2 rounded-xl bg-surface-subtle dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-brand-50 dark:hover:bg-brand-900/20 hover:text-brand-700 dark:hover:text-brand-300 transition-colors"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((msg) => (
              <div
                key={msg.id}
                className={cn(
                  'flex gap-2 items-end',
                  msg.role === 'user' ? 'flex-row-reverse' : 'flex-row',
                )}
              >
                {msg.role === 'assistant' && (
                  <div className="h-7 w-7 rounded-full bg-brand-100 dark:bg-brand-900/40 flex items-center justify-center shrink-0 mb-0.5">
                    <svg className="h-4 w-4 text-brand-600 dark:text-brand-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M12 2a10 10 0 0 1 0 20M12 2a10 10 0 0 0 0 20M12 8v4M12 16h.01" />
                    </svg>
                  </div>
                )}

                <div
                  className={cn(
                    'max-w-[75%] rounded-2xl px-3 py-2 text-sm leading-relaxed',
                    msg.role === 'user'
                      ? 'bg-brand-600 text-white rounded-br-sm'
                      : 'bg-slate-100 dark:bg-slate-800 text-slate-800 dark:text-slate-200 rounded-bl-sm',
                    msg.isTyping && 'min-w-[60px]',
                  )}
                >
                  {msg.isTyping ? (
                    <TypingIndicator />
                  ) : (
                    <span className="whitespace-pre-wrap">{msg.content}</span>
                  )}
                </div>
              </div>
            ))}

            {error && (
              <div className="flex items-center gap-2 px-3 py-2 rounded-xl bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 text-xs">
                <svg className="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M12 9v4M12 17h.01M4.93 19h14.14L12 5z" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                {error}
              </div>
            )}

            <div ref={bottomRef} />
          </div>

          {/* Input area */}
          <div className="px-4 py-3 border-t border-slate-200 dark:border-slate-700">
            <div className="flex items-end gap-2">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                rows={1}
                placeholder="Ask anything... (Enter to send)"
                disabled={sending}
                className={cn(
                  'flex-1 resize-none rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2 text-sm',
                  'placeholder:text-slate-400 focus:border-brand-500 focus:ring-2 focus:ring-brand-200 outline-none transition-colors',
                  'disabled:opacity-60 dark:text-slate-100 max-h-32',
                )}
                style={{ minHeight: 40 }}
              />
              <button
                onClick={handleSend}
                disabled={sending || !input.trim()}
                className="h-10 w-10 rounded-xl bg-brand-600 hover:bg-brand-500 disabled:opacity-50 disabled:cursor-not-allowed text-white flex items-center justify-center shrink-0 transition-colors"
              >
                <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z" />
                </svg>
              </button>
            </div>
            <p className="text-[10px] text-slate-400 mt-1.5 text-center">
              Shift+Enter for newline · Powered by Claude
            </p>
          </div>
        </div>
      )}
    </>
  );
}

function TypingIndicator() {
  return (
    <div className="flex items-center gap-1 py-0.5 px-1">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="h-2 w-2 rounded-full bg-slate-400 dark:bg-slate-500 animate-bounce"
          style={{ animationDelay: `${i * 150}ms`, animationDuration: '800ms' }}
        />
      ))}
    </div>
  );
}
