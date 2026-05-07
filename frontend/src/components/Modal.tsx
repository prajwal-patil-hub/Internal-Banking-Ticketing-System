import { useEffect } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { X } from 'lucide-react';
import { cn } from '@/lib/cn';

interface Props {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: React.ReactNode;
  className?: string;
}

export function Modal({ open, onClose, title, description, children, className }: Props) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = '';
    };
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          key="backdrop"
          className="fixed inset-0 z-50 grid place-items-center p-4"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18 }}
          onClick={onClose}
          style={{ background: 'rgba(17,24,39,0.32)', backdropFilter: 'blur(8px)' }}
        >
          <motion.div
            key="card"
            initial={{ opacity: 0, y: 12, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.98 }}
            transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-labelledby="modal-title"
            className={cn(
              'glass-strong w-full max-w-lg rounded-4xl p-6 sm:p-7',
              className,
            )}
          >
            <div className="flex items-start justify-between gap-4 mb-5">
              <div className="min-w-0">
                <h2 id="modal-title" className="text-xl font-semibold tracking-tightish text-ink truncate">
                  {title}
                </h2>
                {description && (
                  <p className="text-sm text-ink-muted mt-1">{description}</p>
                )}
              </div>
              <button
                onClick={onClose}
                aria-label="Close"
                className="h-9 w-9 -mr-1 -mt-1 grid place-items-center rounded-pill text-ink-muted hover:text-ink hover:bg-white/70 transition-colors"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            {children}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
