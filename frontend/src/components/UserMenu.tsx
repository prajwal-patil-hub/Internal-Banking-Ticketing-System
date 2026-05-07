import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { useAuth } from '@/store/auth';
import { useTheme } from '@/store/theme';
import { logout as apiLogout } from '@/features/auth/api';
import { cn } from '@/lib/cn';

function userInitials(name: string): string {
  return (
    name
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((p) => p[0]?.toUpperCase())
      .join('') || '?'
  );
}

/**
 * Avatar that opens a dropdown with the user's name, role, theme toggle, and
 * sign-out. Keeps the topbar compact at every breakpoint.
 */
export function UserMenu() {
  const { user, refreshToken, clear } = useAuth();
  const { theme, toggle } = useTheme();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

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

  const onSignOut = async () => {
    setOpen(false);
    try { await apiLogout(refreshToken); } catch { /* ignore */ }
    clear();
    nav('/login', { replace: true });
  };

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className={cn(
          'h-9 w-9 rounded-full bg-brand-100 hover:bg-brand-200 flex items-center justify-center',
          'text-brand-700 font-semibold transition-colors',
          'dark:bg-brand-700 dark:hover:bg-brand-600 dark:text-white',
        )}
        aria-label="Open user menu"
        aria-expanded={open}
      >
        {user ? userInitials(user.full_name) : '?'}
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-64 bg-surface dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-2xl shadow-cardLg z-40 overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-100 dark:border-slate-800">
            <div className="font-semibold truncate">{user?.full_name}</div>
            <div className="text-xs text-slate-500 truncate">{user?.email}</div>
            <div className="mt-1 inline-block text-[10px] uppercase tracking-wide font-semibold text-brand-700 dark:text-brand-200 bg-brand-50 dark:bg-brand-900/40 px-2 py-0.5 rounded-full">
              {user?.role.replace('_', ' ')}
            </div>
          </div>

          <button
            onClick={() => { toggle(); }}
            className="w-full px-4 py-2.5 text-sm text-left hover:bg-surface-muted dark:hover:bg-slate-800 flex items-center justify-between"
          >
            <span>Theme</span>
            <span className="text-xs text-slate-500 capitalize">{theme === 'dark' ? 'Dark' : 'Light'} · click to switch</span>
          </button>

          <button
            onClick={onSignOut}
            className="w-full px-4 py-2.5 text-sm text-left text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 border-t border-slate-100 dark:border-slate-800"
          >
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}
