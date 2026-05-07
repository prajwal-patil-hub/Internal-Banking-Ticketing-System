import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { Bell, CheckCheck } from 'lucide-react';

import { Badge } from '@/components/Badge';
import {
  listNotifications,
  markAllRead,
  markRead,
  unreadCount,
  type NotificationItem,
} from './api';
import { formatRelative } from '@/lib/format';
import { cn } from '@/lib/cn';

const POLL_MS = 30_000;

export function NotificationBell() {
  const qc = useQueryClient();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const count = useQuery({
    queryKey: ['notifications', 'unread'],
    queryFn: unreadCount,
    refetchInterval: POLL_MS,
  });
  const list = useQuery({
    queryKey: ['notifications', 'recent'],
    queryFn: () => listNotifications({ page: 1, size: 12 }),
    enabled: open,
    refetchInterval: open ? POLL_MS : false,
  });

  const read = useMutation({
    mutationFn: (id: string) => markRead(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['notifications', 'unread'] });
      qc.invalidateQueries({ queryKey: ['notifications', 'recent'] });
    },
  });

  const allRead = useMutation({
    mutationFn: markAllRead,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['notifications', 'unread'] });
      qc.invalidateQueries({ queryKey: ['notifications', 'recent'] });
    },
  });

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', onClick);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onClick);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const handleClick = (n: NotificationItem) => {
    if (!n.read_at) read.mutate(n.id);
    const tid = (n.payload as { ticket_id?: string }).ticket_id;
    if (tid) nav(`/tickets/${tid}`);
    setOpen(false);
  };

  const unread = count.data ?? 0;

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className={cn(
          'relative h-10 w-10 rounded-pill grid place-items-center transition-colors',
          'text-ink hover:text-brand-600 hover:bg-white/70',
        )}
        aria-label="Notifications"
      >
        <Bell className="h-[18px] w-[18px]" />
        {unread > 0 && (
          <motion.span
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] px-1 rounded-pill bg-danger text-white text-[10px] font-bold grid place-items-center shadow-soft"
          >
            {unread > 99 ? '99+' : unread}
          </motion.span>
        )}
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -4, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.98, transition: { duration: 0.12 } }}
            transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
            className="absolute right-0 mt-2 w-96 max-h-[480px] overflow-hidden z-40 origin-top-right"
          >
            <div className="glass-strong rounded-3xl flex flex-col">
              <div className="px-4 py-3 border-b border-white/40 flex items-center justify-between gap-2">
                <div className="font-semibold text-ink">Notifications</div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-ink-muted">{unread} unread</span>
                  <button
                    onClick={() => allRead.mutate()}
                    disabled={unread === 0 || allRead.isPending}
                    className="btn-ghost px-2 py-1 text-xs disabled:opacity-50"
                    title="Mark all as read"
                  >
                    <CheckCheck className="h-3.5 w-3.5" />
                    Mark all read
                  </button>
                </div>
              </div>

              <div className="overflow-auto max-h-[400px]">
                {list.isLoading && (
                  <p className="p-6 text-sm text-ink-muted text-center">Loading…</p>
                )}
                {!list.isLoading && (list.data?.items.length ?? 0) === 0 && (
                  <p className="p-8 text-sm text-ink-muted text-center">You're all caught up.</p>
                )}
                <ul className="divide-y divide-white/40">
                  {list.data?.items.map((n) => (
                    <li key={n.id}>
                      <button
                        onClick={() => handleClick(n)}
                        className={cn(
                          'w-full text-left p-4 transition-colors',
                          !n.read_at ? 'bg-brand-50/50 hover:bg-brand-50' : 'hover:bg-white/60',
                        )}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <span className="text-sm font-semibold text-ink truncate">{n.subject}</span>
                          {!n.read_at && <Badge tone="info">new</Badge>}
                        </div>
                        <p className="text-xs text-ink-muted mt-1 line-clamp-2">{n.body}</p>
                        <p className="text-2xs text-ink-subtle mt-1.5">{formatRelative(n.created_at)}</p>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
