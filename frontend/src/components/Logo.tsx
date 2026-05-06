import { cn } from '@/lib/cn';

interface Props {
  className?: string;
  variant?: 'light' | 'dark';
}

export function Logo({ className, variant = 'light' }: Props) {
  const fg = variant === 'light' ? 'text-white' : 'text-brand-700';
  return (
    <div className={cn('flex items-center gap-2 select-none', className)}>
      <span
        className={cn(
          'inline-flex h-8 w-8 items-center justify-center rounded-xl font-bold',
          variant === 'light'
            ? 'bg-white/15 text-white'
            : 'bg-brand-600 text-white',
        )}
      >
        S
      </span>
      <span className={cn('font-bold tracking-wide', fg)}>SUCCESS</span>
    </div>
  );
}
