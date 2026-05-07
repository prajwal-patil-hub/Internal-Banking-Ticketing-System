import { cn } from '@/lib/cn';

interface Props extends React.HTMLAttributes<HTMLDivElement> {
  padded?: boolean;
}

/**
 * Surface primitive. Light = white card with brand-tinted shadow.
 * Dark  = slate-900 with a 1px slate-800 border (no shadow).
 */
export function Card({ className, padded = true, ...rest }: Props) {
  return (
    <div
      className={cn(
        'bg-surface rounded-2xl shadow-card text-slate-900',
        'dark:bg-slate-900 dark:text-slate-100 dark:shadow-none dark:border dark:border-slate-800',
        padded && 'p-6',
        className,
      )}
      {...rest}
    />
  );
}
