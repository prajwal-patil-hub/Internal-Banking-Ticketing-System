import { useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';

import { Logo } from '@/components/Logo';
import { AIChatWidget } from '@/components/AIChatWidget';
import { useTheme } from '@/store/theme';
import { cn } from '@/lib/cn';
import { useAuth, type AuthUser } from '@/store/auth';
import {
  canManageOrg,
  canManageUsers,
  canQueryKnowledgeBase,
  canViewAudit,
  canViewBranches,
  canViewEscalations,
  canViewReports,
  canViewSLA,
} from '@/lib/permissions';
import { logout as apiLogout } from '@/features/auth/api';

interface NavItem {
  to: string;
  label: string;
  icon: string;
  /**
   * Whether this viewer may open the route. Omit for routes open to every
   * signed-in user.
   *
   * A predicate from `@/lib/permissions`, not a role list. The sidebar used to
   * carry its own `roles: Role[]` on each item, which made it a third copy of
   * rules already stated in `authz.py` and in the router's `RequireAuth`
   * guards. Three copies of one rule drift, and the sidebar is what tells a
   * user a route exists — so a sidebar that disagrees with the router either
   * shows links that 403 or hides pages the user is entitled to.
   */
  can?: (u: AuthUser | null) => boolean;
  badge?: string;
}

interface NavSection {
  /** Rendered as a small heading above the group. Null for the top group,
   *  which needs no label — Dashboard and Tickets are where everyone starts. */
  title: string | null;
  items: NavItem[];
}

/**
 * The sidebar, grouped.
 *
 * It was a flat list of eleven links, which made every destination look
 * equally weighted: "Knowledge Base" sat between "Escalations" and "Branches"
 * as though curating the document corpus were the same kind of act as opening
 * a queue. Grouping states what each area is for, and gives the knowledge base
 * a home it can grow into rather than one more row.
 *
 * A section renders only if the viewer can see at least one item inside it, so
 * an agent never sees an empty "Administration" heading.
 */
const NAV_SECTIONS: NavSection[] = [
  {
    title: null,
    items: [
      { to: '/dashboard', label: 'Dashboard', icon: 'M3 12l9-9 9 9M5 10v10h14V10', badge: 'AI' },
      { to: '/tickets',   label: 'Tickets',   icon: 'M4 7h16M4 12h16M4 17h10' },
    ],
  },
  {
    title: 'Knowledge Base',
    items: [
      // Curation is admin-only, but querying is not: the whole point of the
      // corpus is that agents and supervisors are answered from it. The route
      // itself hides the upload and grant controls from anyone who cannot use
      // them — see KnowledgeBasePage.
      { to: '/knowledge', label: 'Documents & Ask', badge: 'RAG',
        icon: 'M4 5a2 2 0 012-2h12v18H6a2 2 0 01-2-2zM8 7h8M8 11h6',
        can: canQueryKnowledgeBase },
    ],
  },
  {
    title: 'Operations',
    items: [
      { to: '/sla',         label: 'SLA Monitor', icon: 'M12 8v4l3 2M21 12a9 9 0 11-18 0 9 9 0 0118 0z',
        can: canViewSLA },
      { to: '/escalations', label: 'Escalations', icon: 'M12 9v4M12 17h.01M4.93 19h14.14L12 5z',
        can: canViewEscalations },
      { to: '/branches',    label: 'Branches',    icon: 'M3 21h18M5 21V8l7-5 7 5v13M9 21v-6h6v6',
        can: canViewBranches },
    ],
  },
  {
    title: 'Administration',
    items: [
      { to: '/org',   label: 'Org Hierarchy', icon: 'M3 21V8l9-5 9 5v13M9 21V12h6v9',
        can: canManageOrg },
      { to: '/users', label: 'Users',         icon: 'M16 11a4 4 0 10-8 0 4 4 0 008 0zM2 21a8 8 0 1116 0',
        can: canManageUsers },
    ],
  },
  {
    title: 'Oversight',
    items: [
      { to: '/reports', label: 'Reports',   icon: 'M9 17v-6M12 17v-4M15 17v-2M5 3h14l1 4H4zM3 7h18v14H3z',
        can: canViewReports },
      { to: '/audit',   label: 'Audit Log', icon: 'M9 12h6M9 16h6M5 4h14v16H5z',
        can: canViewAudit },
    ],
  },
  {
    title: 'Account',
    items: [
      // No `can`: two-factor authentication is a personal account setting, so
      // every signed-in user needs to reach it.
      { to: '/security', label: 'Security', icon: 'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10zM9 12l2 2 4-4' },
    ],
  },
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

/**
 * The header breadcrumb.
 *
 * It used to read "SUCCESS Bank / Internal Ticketing" on every route — the
 * same two words on all fourteen screens, which is decoration, not a
 * breadcrumb. It now names where you actually are, which is the one thing a
 * persistent header is for.
 *
 * Derived from the nav table rather than a second hand-written map, so a
 * renamed sidebar item cannot leave a stale crumb behind it.
 */
function useBreadcrumb(): string[] {
  const { pathname } = useLocation();

  for (const section of NAV_SECTIONS) {
    for (const item of section.items) {
      if (pathname === item.to || pathname.startsWith(`${item.to}/`)) {
        const leaf =
          pathname === item.to
            ? []
            // The ticket number is not known here, so name the kind of thing.
            : [pathname.endsWith('/new') ? 'New' : 'Detail'];
        return [...(section.title ? [section.title] : []), item.label, ...leaf];
      }
    }
  }
  return ['Internal Ticketing'];
}

function userInitials(name: string): string {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]?.toUpperCase()).join('') || '?';
}

export function AppLayout() {
  const { theme, toggle } = useTheme();
  const { user, refreshToken, clear } = useAuth();
  const nav = useNavigate();
  const [searchValue, setSearchValue] = useState('');
  const crumbs = useBreadcrumb();

  // Filter items first, then drop any section left empty — otherwise an agent
  // sees an "Administration" heading with nothing under it.
  const visibleSections = NAV_SECTIONS
    .map((section) => ({
      ...section,
      items: section.items.filter((i) => !i.can || i.can(user)),
    }))
    .filter((section) => section.items.length > 0);

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
      className="min-h-full grid bg-[var(--bg)]"
      style={{ gridTemplateColumns: 'var(--sidebar-width, 220px) 1fr' }}
    >
      {/* ── Sidebar ─────────────────────────────────────────────────────── */}
      <aside className="bg-brand-600 dark:bg-brand-700 text-white flex flex-col gap-6 py-4 px-3">
        {/* Logo */}
        <div className="px-2">
          <Logo />
        </div>

        {/* Nav items */}
        <nav className="flex flex-col gap-3 flex-1">
          {visibleSections.map((section) => (
            <div key={section.title ?? 'main'} className="flex flex-col gap-0.5">
              {section.title && (
                <h2 className="px-2.5 pt-1 pb-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-white/45">
                  {section.title}
                </h2>
              )}
              {section.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    cn(
                      'flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-sm font-medium transition-colors',
                      isActive
                        ? 'bg-white/15 text-white border-l-2 border-white shadow-sm'
                        : 'text-white/80 hover:bg-white/10 hover:text-white',
                    )
                  }
                >
                  <Icon d={item.icon} />
                  <span className="flex-1 truncate">{item.label}</span>
                  {item.badge && (
                    <span className="px-1.5 py-0.5 rounded bg-white/15 text-white/90 text-[9px] font-bold tracking-wider leading-none">
                      {item.badge}
                    </span>
                  )}
                </NavLink>
              ))}
            </div>
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
          className="shrink-0 px-6 flex items-center justify-between sticky top-0 z-20 bg-[var(--bg)]"
          style={{ height: 'var(--header-height, 56px)', boxShadow: '0 2px 8px var(--sh-dark)' }}
        >
          {/* Breadcrumb */}
          <nav aria-label="Breadcrumb" className="flex items-center gap-2 text-xs text-[var(--tx-3)] min-w-0">
            <span className="font-medium text-[var(--tx-2)] shrink-0">SUCCESS Bank</span>
            {crumbs.map((crumb, i) => (
              <span key={crumb} className="flex items-center gap-2 min-w-0">
                <span aria-hidden="true">/</span>
                <span className={cn('truncate', i === crumbs.length - 1 && 'text-[var(--tx-2)]')}>
                  {crumb}
                </span>
              </span>
            ))}
          </nav>

          {/* Search + user */}
          <div className="flex items-center gap-3">
            {/* Search */}
            <form onSubmit={handleSearch} className="relative hidden md:block">
              <svg
                className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-[var(--tx-3)] pointer-events-none"
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
                <span className="text-xs font-medium text-[var(--tx)]">{user?.full_name}</span>
                <span className="text-[10px] text-[var(--tx-3)] capitalize">{user?.role.replace('_', ' ')}</span>
              </div>
              <div className="h-8 w-8 rounded-full bg-brand-100 dark:bg-brand-900/50 flex items-center justify-center text-brand-700 dark:text-brand-300 text-xs font-bold">
                {user ? userInitials(user.full_name) : 'SB'}
              </div>
              <button
                onClick={onLogout}
                className="text-xs text-[var(--tx-3)] hover:text-[var(--tx)] transition-colors"
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
