import { cn } from '@/lib/cn';

interface Props {
  className?: string;
  rounded?: 'sm' | 'md' | 'lg' | 'xl' | '2xl' | '3xl' | 'pill';
}

const radii = {
  sm: 'rounded',
  md: 'rounded-md',
  lg: 'rounded-lg',
  xl: 'rounded-xl',
  '2xl': 'rounded-2xl',
  '3xl': 'rounded-3xl',
  pill: 'rounded-pill',
} as const;

export function Skeleton({ className, rounded = 'lg' }: Props) {
  return (
    <div
      className={cn(
        'animate-pulse',
        radii[rounded],
        className,
      )}
      style={{
        background:
          'linear-gradient(90deg, rgba(99,102,241,0.06) 0%, rgba(99,102,241,0.10) 50%, rgba(99,102,241,0.06) 100%)',
      }}
    />
  );
}
