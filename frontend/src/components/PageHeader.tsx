import type { ReactNode } from 'react';
import { cn } from '@/lib/cn';

interface Props {
  /** The page title. One per page — this is the `<h1>`. */
  title: ReactNode;
  /** The line under the title. Usually a count or a one-line description. */
  subtitle?: ReactNode;
  /** Buttons, pills or status shown on the right of the title row. */
  actions?: ReactNode;
  /** Shown left of the title — the back arrow on Create Ticket, for instance. */
  leading?: ReactNode;
  className?: string;
}

/**
 * The page title block.
 *
 * Every page used to draw its own, and twelve hand-rolled copies had drifted
 * into three title sizes (`text-lg`, `text-xl`, `text-2xl`), two colour systems
 * (`text-slate-900 dark:text-slate-100` on three pages, `var(--tx)` on the
 * rest) and four vertical rhythms (`gap-4`, `gap-5`, `gap-6`, `space-y-6`).
 * Walking the app, each screen looked like it belonged to a slightly different
 * product — which is exactly what it was.
 *
 * The raw `slate-*` pages are the reason this is a component rather than a
 * documented convention. A convention drifts silently; three pages had already
 * stopped following the theme tokens, so a change to `--tx-3` moved nine page
 * subtitles and left three behind.
 */
export function PageHeader({ title, subtitle, actions, leading, className }: Props) {
  return (
    <div className={cn('flex items-start justify-between gap-3 flex-wrap', className)}>
      <div className="flex items-start gap-2.5 min-w-0">
        {leading}
        <div className="min-w-0">
          <h1 className="text-xl font-semibold tracking-tight text-[var(--tx)]">{title}</h1>
          {subtitle && (
            <p className="text-xs text-[var(--tx-3)] mt-0.5">{subtitle}</p>
          )}
        </div>
      </div>
      {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
    </div>
  );
}

/**
 * The standard page shell: one vertical rhythm for every route.
 *
 * `gap-5` is the value nine of the twelve pages already used, so this moves the
 * three outliers rather than the majority.
 */
export function PageShell({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn('flex flex-col gap-5', className)}>{children}</div>;
}

/**
 * A "refreshing…" indicator, previously copy-pasted into several pages with
 * a hard-coded `bg-emerald-400` that ignored the theme's own success token.
 */
export function RefreshingDot({ label = 'Refreshing…' }: { label?: string }) {
  return (
    <span className="flex items-center gap-1">
      <span className="h-1.5 w-1.5 rounded-full bg-[var(--ok)] animate-pulse inline-block" />
      {label}
    </span>
  );
}
