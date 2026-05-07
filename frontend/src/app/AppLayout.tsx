import { useEffect, useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import {
  LayoutDashboard,
  Inbox,
  Activity,
  AlertTriangle,
  Building2,
  Users,
  ScrollText,
  Search,
  Menu,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

import { Logo } from '@/components/Logo';
import { ToastViewport } from '@/components/Toast';
import { UserMenu } from '@/components/UserMenu';
import { cn } from '@/lib/cn';
import { useAuth, type Role } from '@/store/auth';
import { NotificationBell } from '@/features/notifications/NotificationBell';

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  roles?: Role[];
}

const NAV: NavItem[] = [
  { to: '/dashboard',    label: 'Dashboard',    icon: LayoutDashboard },
  { to: '/tickets',      label: 'Tickets',      icon: Inbox },
  { to: '/sla',          label: 'SLA Monitor',  icon: Activity,        roles: ['admin', 'supervisor'] },
  { to: '/escalations',  label: 'Escalations',  icon: AlertTriangle,   roles: ['admin', 'supervisor'] },
  { to: '/branches',     label: 'Branches',     icon: Building2,       roles: ['admin'] },
  { to: '/users',        label: 'Users',        icon: Users,           roles: ['admin'] },
  { to: '/audit',        label: 'Audit Log',    icon: ScrollText,      roles: ['auditor', 'admin'] },
];

export function AppLayout() {
  const { user } = useAuth();
  const loc = useLocation();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  useEffect(() => { setMobileNavOpen(false); }, [loc.pathname]);

  useEffect(() => {
    if (mobileNavOpen) {
      const prev = document.body.style.overflow;
      document.body.style.overflow = 'hidden';
      return () => { document.body.style.overflow = prev; };
    }
  }, [mobileNavOpen]);

  const visibleNav = NAV.filter((i) => !i.roles || (user && i.roles.includes(user.role)));

  return (
    <div className="min-h-screen flex">
      {/* ─────────────── Sidebar ─────────────── */}
      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-40 w-[270px] p-4 transition-transform duration-300 ease-smooth',
          mobileNavOpen ? 'translate-x-0' : '-translate-x-full',
          'lg:static lg:translate-x-0 lg:shrink-0',
        )}
      >
        <div className="glass rounded-4xl h-full p-5 flex flex-col gap-7">
          <Logo size="md" />

          <nav className="flex flex-col gap-1">
            <span className="label px-3 mb-1">Operations</span>
            {visibleNav.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    cn(
                      'group flex items-center gap-3 px-3 py-2.5 rounded-2xl text-sm font-medium',
                      'transition-all duration-200 ease-smooth',
                      isActive
                        ? 'text-brand-700 bg-sidebar-active shadow-soft'
                        : 'text-ink-muted hover:text-ink hover:bg-white/60 hover:translate-x-0.5',
                    )
                  }
                >
                  {({ isActive }) => (
                    <>
                      <Icon
                        className={cn(
                          'h-[18px] w-[18px] shrink-0 transition-colors',
                          isActive ? 'text-brand-600' : 'text-ink-subtle group-hover:text-brand-500',
                        )}
                        strokeWidth={2}
                      />
                      <span className="flex-1">{item.label}</span>
                      {isActive && (
                        <motion.span
                          layoutId="active-dot"
                          className="h-1.5 w-1.5 rounded-pill bg-brand-600"
                          transition={{ type: 'spring', bounce: 0.2, duration: 0.35 }}
                        />
                      )}
                    </>
                  )}
                </NavLink>
              );
            })}
          </nav>

          <div className="mt-auto">
            <div className="glass-subtle rounded-2xl p-4">
              <div className="text-xs font-semibold text-ink mb-1">SUCCESS Bank · v0.1.0</div>
              <div className="text-2xs text-ink-muted leading-relaxed">
                Internal operations platform.
              </div>
            </div>
          </div>
        </div>
      </aside>

      {/* Mobile drawer backdrop */}
      <AnimatePresence>
        {mobileNavOpen && (
          <motion.button
            aria-label="Close menu"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setMobileNavOpen(false)}
            className="fixed inset-0 z-30 lg:hidden"
            style={{ background: 'rgba(17,24,39,0.32)', backdropFilter: 'blur(8px)' }}
          />
        )}
      </AnimatePresence>

      {/* ─────────────── Main column ─────────────── */}
      <div className="flex flex-col min-w-0 flex-1">
        <header className="sticky top-0 z-20 px-4 sm:px-6 lg:px-8 pt-4">
          <div className="glass rounded-3xl h-16 px-4 sm:px-5 flex items-center gap-3">
            <button
              className="lg:hidden btn-ghost p-2"
              aria-label="Open menu"
              onClick={() => setMobileNavOpen(true)}
            >
              <Menu className="h-5 w-5" />
            </button>

            <div className="relative flex-1 max-w-xl">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-ink-subtle pointer-events-none" />
              <input
                className="input pl-9 py-2 rounded-2xl bg-white/40 border-white/40"
                placeholder="Search tickets, branches, users…"
              />
              <kbd className="hidden md:inline-flex absolute right-2 top-1/2 -translate-y-1/2 items-center text-2xs font-medium text-ink-muted bg-white/70 border border-white/60 rounded-md px-1.5 py-0.5">
                ⌘K
              </kbd>
            </div>

            <div className="flex items-center gap-2 sm:gap-3 shrink-0 ml-auto">
              <NotificationBell />
              <UserMenu />
            </div>
          </div>
        </header>

        <main className="px-4 sm:px-6 lg:px-8 py-6 sm:py-8 max-w-[1600px] w-full mx-auto">
          <Outlet />
        </main>
      </div>

      <ToastViewport />
    </div>
  );
}
