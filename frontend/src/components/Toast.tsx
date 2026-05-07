import { useEffect } from 'react';
import { create } from 'zustand';
import { AnimatePresence, motion } from 'framer-motion';
import { CheckCircle2, AlertTriangle, Info, XCircle, X } from 'lucide-react';
import { cn } from '@/lib/cn';

export type ToastTone = 'info' | 'success' | 'warning' | 'danger';

interface Toast {
  id: string;
  tone: ToastTone;
  message: string;
}

interface ToastState {
  toasts: Toast[];
  push: (t: Omit<Toast, 'id'>) => void;
  dismiss: (id: string) => void;
}

export const useToasts = create<ToastState>((set) => ({
  toasts: [],
  push: (t) => {
    const id = Math.random().toString(36).slice(2);
    set((s) => ({ toasts: [...s.toasts, { ...t, id }] }));
    setTimeout(() => {
      set((s) => ({ toasts: s.toasts.filter((x) => x.id !== id) }));
    }, 4500);
  },
  dismiss: (id) => set((s) => ({ toasts: s.toasts.filter((x) => x.id !== id) })),
}));

const toneConfig: Record<ToastTone, { icon: typeof Info; ring: string; text: string }> = {
  info:    { icon: Info,           ring: 'ring-info-soft',    text: 'text-info-deep' },
  success: { icon: CheckCircle2,   ring: 'ring-success-soft', text: 'text-success-deep' },
  warning: { icon: AlertTriangle,  ring: 'ring-warning-soft', text: 'text-warning-deep' },
  danger:  { icon: XCircle,        ring: 'ring-danger-soft',  text: 'text-danger-deep' },
};

export function ToastViewport() {
  const { toasts, dismiss } = useToasts();

  useEffect(() => {
    if (toasts.length === 0) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') toasts.forEach((t) => dismiss(t.id));
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [toasts, dismiss]);

  return (
    <div className="fixed top-4 right-4 z-[60] flex flex-col gap-2 w-[min(380px,90vw)] pointer-events-none">
      <AnimatePresence>
        {toasts.map((t) => {
          const cfg = toneConfig[t.tone];
          const Icon = cfg.icon;
          return (
            <motion.div
              key={t.id}
              initial={{ opacity: 0, y: -8, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, x: 12, transition: { duration: 0.15 } }}
              transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
              className={cn(
                'glass-strong rounded-2xl px-4 py-3 text-sm flex items-start gap-3 pointer-events-auto',
              )}
            >
              <Icon className={cn('h-5 w-5 mt-0.5 shrink-0', cfg.text)} />
              <span className="flex-1 text-ink">{t.message}</span>
              <button
                onClick={() => dismiss(t.id)}
                className="text-ink-muted hover:text-ink transition-colors"
                aria-label="Dismiss"
              >
                <X className="h-4 w-4" />
              </button>
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
