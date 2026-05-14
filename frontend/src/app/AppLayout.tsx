import { useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';

import { Logo } from '@/components/Logo';
import { AIChatWidget } from '@/components/AIChatWidget';
import { useTheme } from '@/store/theme';
import { cn } from '@/lib/cn';
import { useAuth, type Role } from '@/store/auth';
import { logout as apiLogout } from '@/features/auth/api';

interface NavItem {
  to: string;
  label: string;
  icon: string;
  roles?: Role[];
  badge?: string;
}

const NAV: NavItem[] = [
  { to: '/dashboard',   label: 'Dashboard',   icon: 'M3 12l9-9 9 9M5 10v10h14V10', badge: 'AI' },
  { to: '/tickets',     label: 'Tickets',     icon: 'M4 7h16M4 12h16M4 17h10' },
  { to: '/sla',         label: 'SLA Monitor', icon: 'M12 8v4l3 2M21 12a9 9 0 11-18 0 9 9 0 0118 0z',
    roles: ['admin', 'supervisor'] },
  { to: '/escalations', label: 'Escalations', icon: 'M12 9v4M12 17h.01M4.93 19h14.14L12 5z',
    roles: ['admin', 'supervisor'] },
  { to: '/branches',    label: 'Branches',    icon: 'M3 21V8l9-5 9 5v13M9 21V12h6v9',
    roles: ['admin'] },
  { to: '/users',       label: 'Users',       icon: 'M16 11a4 4 0 10-8 0 4 4 0 008 0zM2 21a8 8 0 1116 0',
    roles: ['admin'] },
  { to: '/audit',       label: 'Audit Log',   icon: 'M9 12h6M9 16h6M5 4h14v16H5z',
    roles: ['auditor', 'admin'] },
];

function Icon({ d, className }: { d: string; className?: string }) {
  return (
    <svg
      className={cn('h-4 w-4 shrink-0', className)}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d={d} />
    </svg>
  );
}

function userInitials(name: string): string {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]?.toUpperCase()).join('') || '?';
}

export function AppLayout() {
  const { theme, toggle } = useTheme();
  const { user, refreshToken, clear } = useAuth();
  const nav = useNavigate();
  const [searchValue, setSearchValue] = useState('');

  const visibleNav = NAV.filter((i) => !i.roles || (user && i.roles.includes(user.role)));

  const onLogout = async () => {
    try { await apiLogout(refreshToken); } catch { /* network errors are fine on logout */ }
    clear();
    nav('/login', { replace: true });
  };

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchValue.trim()) {
      nav(`/tickets?q=${encodeURIComponent(searchValue.trim())}`);
      setSearchValue('');
    }
  };

  return (
    <div
      className="min-h-full grid bg-surface-muted dark:bg-slate-950"
      style={{ gridTemplateColumns: 'var(--sidebar-width, 220px) 1fr' }}
    >
      {/* ── Sidebar ─────────────────────────────────────────────────────── */}
      <aside className="bg-brand-600 dark:bg-brand-700 text-white flex flex-col gap-6 py-4 px-3">
        {/* Logo */}
        <div className="px-2">
          <Logo />
        </div>

        {/* Nav items */}
        <nav className="flex flex-col gap-0.5 flex-1">
          {visibleNav.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-white text-brand-700 shadow-sm'
                    : 'text-white/80 hover:bg-white/10 hover:text-white',
                )
              }
            >
              <Icon d={item.icon} />
              <span className="flex-1 truncate">{item.label}</span>
              {item.badge && (
                <span className="px-1.5 py-0.5 rounded bg-accent-500/30 text-accent-100 text-[9px] font-bold tracking-wider leading-none">
                  {item.badge}
                </span>
              )}
            </NavLink>
          ))}
        </nav>

        {/* Footer: version + theme */}
        <div className="flex items-center justify-between px-2 text-white/60 text-xs">
          <span className="font-mono">v0.1.0</span>
          <button
            onClick={toggle}
            title={theme === 'dark' ? 'Switch to light' : 'Switch to dark'}
            className="h-7 w-7 rounded-lg flex items-center justify-center bg-white/10 hover:bg-white/20 transition-colors"
          >
            {theme === 'dark' ? (
              <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="5" />
                <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" />
              </svg>
            ) : (
              <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
              </svg>
            )}
          </button>
        </div>
      </aside>

      {/* ── Main area ───────────────────────────────────────────────────── */}
      <div className="flex flex-col min-h-0 overflow-auto">
        {/* Header */}
        <header
          className="shrink-0 px-6 flex items-center justify-between border-b border-slate-200/70 bg-white/70 backdrop-blur-sm dark:bg-slate-900/70 dark:border-slate-800 sticky top-0 z-20"
          style={{ height: 'var(--header-height, 56px)' }}
        >
          {/* Breadcrumb */}
          <div className="flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
            <span className="font-medium text-slate-700 dark:text-slate-300">SUCCESS Bank</span>
            <span className="text-slate-300 dark:text-slate-700">/</span>
            <span>Internal Ticketing</span>
          </div>

          {/* Search + user */}
          <div className="flex items-center gap-3">
            {/* Search */}
            <form onSubmit={handleSearch} className="relative hidden md:block">
              <svg
                className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-400 pointer-events-none"
                viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                strokeLinecap="round" strokeLinejoin="round"
              >
                <circle cx="11" cy="11" r="8" />
                <path d="M21 21l-4.35-4.35" />
              </svg>
              <input
                className="input pl-8 py-1.5 w-56 text-xs h-8"
                placeholder="Search tickets… (↵)"
                value={searchValue}
                onChange={(e) => setSearchValue(e.target.value)}
              />
            </form>

            {/* User avatar + role */}
            <div className="flex items-center gap-2">
              <div className="hidden md:flex flex-col items-end leading-tight">
                <span className="text-xs font-medium text-slate-700 dark:text-slate-300">{user?.full_name}</span>
                <span className="text-[10px] text-slate-400 capitalize">{user?.role.replace('_', ' ')}</span>
              </div>
              <div className="h-8 w-8 rounded-full bg-brand-100 dark:bg-brand-900/50 flex items-center justify-center text-brand-700 dark:text-brand-300 text-xs font-bold">
                {user ? userInitials(user.full_name) : 'SB'}
              </div>
              <button
                onClick={onLogout}
                className="text-xs text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200 transition-colors"
                title="Sign out"
              >
                <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9" />
                </svg>
              </button>
            </div>
          </div>
        </header>

        {/* Page content */}
        <main className="p-6 flex-1">
          <Outlet />
        </main>
      </div>

      {/* Floating AI chat */}
      <AIChatWidget />
    </div>
  );
}
