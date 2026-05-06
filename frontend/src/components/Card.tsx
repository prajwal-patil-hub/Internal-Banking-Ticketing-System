import { cn } from '@/lib/cn';

interface Props extends React.HTMLAttributes<HTMLDivElement> {
  padded?: boolean;
}

export function Card({ className, padded = true, ...rest }: Props) {
  return (
    <div
      className={cn(
        'bg-surface rounded-2xl shadow-card',
        padded ? 'p-6' : '',
        'dark:bg-slate-900 dark:shadow-none dark:border dark:border-slate-800',
        className,
      )}
      {...rest}
    />
  );
}
