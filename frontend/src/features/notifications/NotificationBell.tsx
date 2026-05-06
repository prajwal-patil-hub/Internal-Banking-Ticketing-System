import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';

import { Badge } from '@/components/Badge';
import { listNotifications, markRead, unreadCount, type NotificationItem } from './api';
import { formatRelative } from '@/lib/format';
import { cn } from '@/lib/cn';

const POLL_MS = 30_000;

export function NotificationBell() {
  const qc = useQueryClient();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);

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

  const handleClick = (n: NotificationItem) => {
    if (!n.read_at) read.mutate(n.id);
    const tid = (n.payload as { ticket_id?: string }).ticket_id;
    if (tid) nav(`/tickets/${tid}`);
    setOpen(false);
  };

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="relative h-9 w-9 rounded-full bg-surface-muted hover:bg-surface-subtle dark:bg-slate-800 flex items-center justify-center"
        aria-label="Notifications"
      >
        <svg className="h-5 w-5 text-slate-700 dark:text-slate-200" viewBox="0 0 24 24" fill="none"
             stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M18 8a6 6 0 10-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 01-3.46 0" />
        </svg>
        {(count.data ?? 0) > 0 && (
          <span className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] px-1 rounded-full bg-red-500 text-white text-[10px] font-bold flex items-center justify-center">
            {(count.data ?? 0) > 99 ? '99+' : count.data}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-96 max-h-[480px] overflow-auto bg-surface dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-2xl shadow-cardLg z-40">
          <div className="p-3 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between">
            <span className="font-semibold">Notifications</span>
            <span className="text-xs text-slate-500">{count.data ?? 0} unread</span>
          </div>

          {list.isLoading && <p className="p-4 text-sm text-slate-400">Loading…</p>}
          {!list.isLoading && (list.data?.items.length ?? 0) === 0 && (
            <p className="p-6 text-sm text-slate-400 text-center">You're all caught up.</p>
          )}
          <ul className="divide-y divide-slate-100 dark:divide-slate-800">
            {list.data?.items.map((n) => (
              <li key={n.id}>
                <button
                  onClick={() => handleClick(n)}
                  className={cn(
                    'w-full text-left p-3 hover:bg-surface-muted dark:hover:bg-slate-800/50',
                    !n.read_at && 'bg-brand-50 dark:bg-brand-900/10',
                  )}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-medium truncate">{n.subject}</span>
                    {!n.read_at && <Badge tone="info">new</Badge>}
                  </div>
                  <p className="text-xs text-slate-500 mt-1 line-clamp-2">{n.body}</p>
                  <p className="text-[11px] text-slate-400 mt-1">{formatRelative(n.created_at)}</p>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
