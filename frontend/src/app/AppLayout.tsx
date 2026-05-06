import { NavLink, Outlet } from 'react-router-dom';
import { Logo } from '@/components/Logo';
import { useTheme } from '@/store/theme';
import { cn } from '@/lib/cn';

interface NavItem {
  to: string;
  label: string;
  icon: string;
  badge?: number;
}

// Phase P0 ships a static nav; later phases gate items by role.
const NAV: NavItem[] = [
  { to: '/dashboard',    label: 'Dashboard',    icon: 'M3 12l9-9 9 9M5 10v10h14V10' },
  { to: '/tickets',      label: 'Tickets',      icon: 'M4 7h16M4 12h16M4 17h10' },
  { to: '/sla',          label: 'SLA Monitor',  icon: 'M12 8v4l3 2M21 12a9 9 0 11-18 0 9 9 0 0118 0z' },
  { to: '/escalations',  label: 'Escalations',  icon: 'M12 9v4M12 17h.01M4.93 19h14.14L12 5z' },
  { to: '/branches',     label: 'Branches',     icon: 'M3 21V8l9-5 9 5v13M9 21V12h6v9' },
  { to: '/users',        label: 'Users',        icon: 'M16 11a4 4 0 10-8 0 4 4 0 008 0zM2 21a8 8 0 1116 0' },
  { to: '/audit',        label: 'Audit Log',    icon: 'M9 12h6M9 16h6M5 4h14v16H5z' },
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
  const { theme, toggle } = useTheme();

  return (
    <div className="min-h-full grid grid-cols-[260px_1fr] bg-surface-muted dark:bg-slate-950">
      {/* Sidebar */}
      <aside className="bg-brand-600 text-white px-5 py-6 flex flex-col gap-8 dark:bg-brand-700">
        <Logo />

        <nav className="flex flex-col gap-1">
          {NAV.map((item) => (
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
              {item.badge != null && (
                <span className="text-xs font-semibold opacity-80">{item.badge}</span>
              )}
            </NavLink>
          ))}
        </nav>

        <div className="mt-auto flex items-center justify-between text-white/80 text-xs">
          <span>v0.1.0</span>
          <button onClick={toggle} className="rounded-lg bg-white/10 hover:bg-white/20 px-3 py-1.5">
            {theme === 'dark' ? 'Light' : 'Dark'}
          </button>
        </div>
      </aside>

      {/* Main */}
      <div className="flex flex-col">
        <header className="h-16 px-8 flex items-center justify-between border-b border-slate-200/70 bg-white/60 backdrop-blur dark:bg-slate-900/60 dark:border-slate-800">
          <div className="flex items-center gap-3">
            <span className="text-sm text-slate-500 dark:text-slate-400">SUCCESS Bank</span>
            <span className="text-slate-300">/</span>
            <span className="text-sm font-medium">Internal Ticketing</span>
          </div>

          <div className="flex items-center gap-3">
            <input
              className="input w-72"
              placeholder="Search tickets, branches, users…"
            />
            <div className="h-9 w-9 rounded-full bg-brand-100 flex items-center justify-center text-brand-700 font-semibold">
              SB
            </div>
          </div>
        </header>

        <main className="p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
