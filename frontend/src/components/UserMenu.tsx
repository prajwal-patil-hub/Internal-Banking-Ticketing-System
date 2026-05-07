import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { LogOut, Moon, Sun, UserCircle2 } from 'lucide-react';

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
          'h-10 w-10 rounded-pill grid place-items-center font-semibold text-sm',
          'transition-all duration-200 ease-smooth',
          'text-white shadow-soft hover:scale-[1.02]',
        )}
        style={{
          background:
            'linear-gradient(135deg, #4F46E5 0%, #6366F1 50%, #8B5CF6 100%)',
        }}
        aria-label="Open user menu"
        aria-expanded={open}
      >
        {user ? userInitials(user.full_name) : '?'}
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -4, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.98, transition: { duration: 0.12 } }}
            transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
            className="absolute right-0 mt-2 w-72 z-40 origin-top-right"
          >
            <div className="glass-strong rounded-3xl p-2 overflow-hidden">
              {/* User block */}
              <div className="px-3 pt-3 pb-3 border-b border-white/40">
                <div className="text-md font-semibold tracking-tightish text-ink truncate">
                  {user?.full_name}
                </div>
                <div className="text-xs text-ink-muted truncate">{user?.email}</div>
                <div className="mt-2 inline-flex items-center gap-1.5 pill-soft">
                  <span className="h-1.5 w-1.5 rounded-pill bg-brand-600" />
                  {user?.role.replace('_', ' ')}
                </div>
              </div>

              <Link
                to="/profile"
                onClick={() => setOpen(false)}
                className="w-full px-3 py-2.5 text-sm flex items-center gap-3 rounded-2xl hover:bg-white/60 transition-colors text-ink"
              >
                <UserCircle2 className="h-4 w-4 text-brand-600" />
                <span className="flex-1 text-left">Your profile</span>
              </Link>

              <button
                onClick={() => toggle()}
                className="w-full px-3 py-2.5 text-sm flex items-center gap-3 rounded-2xl hover:bg-white/60 transition-colors"
              >
                {theme === 'dark' ? (
                  <Sun className="h-4 w-4 text-warning-deep" />
                ) : (
                  <Moon className="h-4 w-4 text-brand-600" />
                )}
                <span className="flex-1 text-left text-ink">Theme</span>
                <span className="text-xs text-ink-muted capitalize">{theme}</span>
              </button>

              <div className="hairline mx-2 my-1" />

              <button
                onClick={onSignOut}
                className="w-full px-3 py-2.5 text-sm flex items-center gap-3 rounded-2xl hover:bg-danger-soft transition-colors text-danger-deep"
              >
                <LogOut className="h-4 w-4" />
                <span className="flex-1 text-left">Sign out</span>
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
