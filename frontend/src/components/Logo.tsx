import { cn } from '@/lib/cn';

interface Props {
  className?: string;
  withWordmark?: boolean;
  size?: 'sm' | 'md' | 'lg';
}

const sizes = {
  sm: { box: 'h-8 w-8', mark: 'text-sm', word: 'text-sm' },
  md: { box: 'h-10 w-10', mark: 'text-base', word: 'text-md' },
  lg: { box: 'h-12 w-12', mark: 'text-lg', word: 'text-xl' },
};

export function Logo({ className, withWordmark = true, size = 'md' }: Props) {
  const s = sizes[size];
  return (
    <div className={cn('flex items-center gap-3 select-none', className)}>
      <span
        className={cn(
          'inline-grid place-items-center rounded-2xl font-bold text-white shadow-glow',
          s.box,
          s.mark,
        )}
        style={{
          background:
            'linear-gradient(135deg, #4F46E5 0%, #6366F1 50%, #8B5CF6 100%)',
        }}
        aria-hidden
      >
        S
      </span>
      {withWordmark && (
        <div className="flex flex-col leading-tight">
          <span className={cn('font-semibold tracking-tight text-ink', s.word)}>
            SUCCESS Bank
          </span>
          <span className="text-2xs uppercase tracking-wider text-ink-muted">
            Internal Operations
          </span>
        </div>
      )}
    </div>
  );
}
