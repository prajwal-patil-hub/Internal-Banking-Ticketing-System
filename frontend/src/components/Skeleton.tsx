import { cn } from '@/lib/cn';

interface Props {
  className?: string;
  rounded?: 'sm' | 'md' | 'lg' | 'xl' | '2xl' | 'full';
}

export function Skeleton({ className, rounded = 'lg' }: Props) {
  const r = {
    sm: 'rounded',
    md: 'rounded-md',
    lg: 'rounded-lg',
    xl: 'rounded-xl',
    '2xl': 'rounded-2xl',
    full: 'rounded-full',
  }[rounded];
  return (
    <div
      className={cn(
        'animate-pulse bg-slate-200/70 dark:bg-slate-800/70',
        r,
        className,
      )}
    />
  );
}
