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

/**
 * Brand mark — Oxford navy seal with brass S monogram.
 */
export function Logo({ className, withWordmark = true, size = 'md' }: Props) {
  const s = sizes[size];
  return (
    <div className={cn('flex items-center gap-3 select-none', className)}>
      <span
        className={cn(
          'relative inline-grid place-items-center rounded-2xl font-bold shadow-glow',
          s.box,
          s.mark,
        )}
        style={{
          background:
            'linear-gradient(135deg, #1F3A5F 0%, #182D49 60%, #0B1929 100%)',
        }}
        aria-hidden
      >
        <span
          className="font-serif"
          style={{ color: '#D9C68B', letterSpacing: '0.02em' }}
        >
          S
        </span>
        {/* brass ring */}
        <span
          className="absolute inset-0 rounded-2xl pointer-events-none"
          style={{ boxShadow: 'inset 0 0 0 1px rgba(184,150,90,0.45)' }}
        />
      </span>
      {withWordmark && (
        <div className="flex flex-col leading-tight">
          <span className={cn('font-semibold tracking-tight text-ink', s.word)}>
            SUCCESS Bank
          </span>
          <span className="text-2xs uppercase tracking-[0.18em] text-brass-600">
            Internal Operations
          </span>
        </div>
      )}
    </div>
  );
}
