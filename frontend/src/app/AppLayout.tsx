import { useEffect, useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';

import { Logo } from '@/components/Logo';
import { ToastViewport } from '@/components/Toast';
import { UserMenu } from '@/components/UserMenu';
import { cn } from '@/lib/cn';
import { useAuth, type Role } from '@/store/auth';
import { NotificationBell } from '@/features/notifications/NotificationBell';

interface NavItem {
  to: string;
  label: string;
  icon: string;
  roles?: Role[];
}

const NAV: NavItem[] = [
  { to: '/dashboard',    label: 'Dashboard',    icon: 'M3 12l9-9 9 9M5 10v10h14V10' },
  { to: '/tickets',      label: 'Tickets',      icon: 'M4 7h16M4 12h16M4 17h10' },
  { to: '/sla',          label: 'SLA Monitor',  icon: 'M12 8v4l3 2M21 12a9 9 0 11-18 0 9 9 0 0118 0z',
    roles: ['admin', 'supervisor'] },
  { to: '/escalations',  label: 'Escalations',  icon: 'M12 9v4M12 17h.01M4.93 19h14.14L12 5z',
    roles: ['admin', 'supervisor'] },
  { to: '/branches',     label: 'Branches',     icon: 'M3 21V8l9-5 9 5v13M9 21V12h6v9',
    roles: ['admin'] },
  { to: '/users',        label: 'Users',        icon: 'M16 11a4 4 0 10-8 0 4 4 0 008 0zM2 21a8 8 0 1116 0',
    roles: ['admin'] },
  { to: '/audit',        label: 'Audit Log',    icon: 'M9 12h6M9 16h6M5 4h14v16H5z',
    roles: ['auditor', 'admin'] },
];

function Icon({ d, className }: { d: string; className?: string }) {
  return (
    <svg className={cn('h-5 w-5 shrink-0', className)} viewBox="0 0 24 24" fill="none"
         stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d={d} />
    </svg>
  );
}

export function AppLayout() {
  const { user } = useAuth();
  const loc = useLocation();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  // Close the mobile drawer whenever the route changes.
  useEffect(() => { setMobileNavOpen(false); }, [loc.pathname]);

  // Lock body scroll when the mobile drawer is open.
  useEffect(() => {
    if (mobileNavOpen) {
      const prev = document.body.style.overflow;
      document.body.style.overflow = 'hidden';
      return () => { document.body.style.overflow = prev; };
    }
  }, [mobileNavOpen]);

  const visibleNav = NAV.filter((i) => !i.roles || (user && i.roles.includes(user.role)));

  return (
    <div className="min-h-screen flex bg-surface-muted dark:bg-slate-950">
      {/*
        Sidebar.
        - lg+   : static flex item, occupies a real 260px column. Content
                  renders next to it via flex-1.
        - <lg   : fixed drawer that slides in from the left.
      */}
      <aside
        className={cn(
          'bg-brand-600 dark:bg-brand-700 text-white px-5 py-6',
          'flex flex-col gap-8 w-[260px] shrink-0',
          // Mobile: fixed drawer.
          'fixed inset-y-0 left-0 z-40 transition-transform',
          mobileNavOpen ? 'translate-x-0' : '-translate-x-full',
          // Desktop: flow with the page, always visible.
          'lg:static lg:translate-x-0 lg:transition-none',
        )}
      >
        <Logo />

        <nav className="flex flex-col gap-1">
          {visibleNav.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-white text-brand-700 shadow-card'
                    : 'text-white/85 hover:bg-white/10',
                )
              }
            >
              <Icon d={item.icon} />
              <span className="flex-1">{item.label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="mt-auto text-white/60 text-xs">
          v0.1.0 · SUCCESS Bank
        </div>
      </aside>

      {/* Mobile backdrop */}
      {mobileNavOpen && (
        <button
          aria-label="Close menu"
          className="fixed inset-0 z-30 bg-slate-900/50 backdrop-blur-sm lg:hidden"
          onClick={() => setMobileNavOpen(false)}
        />
      )}

      {/* Main column — flex-1 so it always fills the remaining width. */}
      <div className="flex flex-col min-w-0 flex-1">
        <header className="h-16 px-4 sm:px-6 lg:px-8 flex items-center justify-between gap-3 border-b border-slate-200/70 bg-white/70 backdrop-blur dark:bg-slate-900/70 dark:border-slate-800 sticky top-0 z-20">
          <div className="flex items-center gap-3 min-w-0">
            <button
              className="lg:hidden btn-ghost p-2"
              aria-label="Open menu"
              onClick={() => setMobileNavOpen(true)}
            >
              <Icon d="M4 6h16M4 12h16M4 18h16" />
            </button>
            <span className="text-sm text-slate-500 dark:text-slate-400 hidden sm:inline">SUCCESS Bank</span>
            <span className="text-slate-300 dark:text-slate-600 hidden sm:inline">/</span>
            <span className="text-sm font-medium truncate">Internal Ticketing</span>
          </div>

          <div className="flex items-center gap-2 sm:gap-3 shrink-0">
            <input className="input w-44 lg:w-72 hidden md:block" placeholder="Search…" />
            <NotificationBell />
            <UserMenu />
          </div>
        </header>

        <main className="p-4 sm:p-6 lg:p-8 max-w-[1600px] w-full mx-auto">
          <Outlet />
        </main>
      </div>

      <ToastViewport />
    </div>
  );
}
