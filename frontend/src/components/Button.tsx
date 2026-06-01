import { forwardRef } from 'react';
import { cn } from '@/lib/cn';

type Variant = 'primary' | 'ghost' | 'danger' | 'subtle';
type Size = 'sm' | 'md' | 'lg';

interface Props extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
}

const base =
  'inline-flex items-center justify-center gap-2 font-medium tracking-wide ' +
  'transition-colors select-none whitespace-nowrap ' +
  'focus-visible:outline-none focus-visible:shadow-focus ' +
  'disabled:cursor-not-allowed disabled:shadow-none';

const variantClass: Record<Variant, string> = {
  primary:
    'rounded-md bg-brand-600 hover:bg-brand-500 active:bg-brand-700 text-cream-50 shadow-card ' +
    'disabled:bg-ink-300 disabled:text-cream-50',
  ghost:
    'rounded-md bg-transparent hover:bg-cream-200 active:bg-cream-300 text-ink-700 ' +
    'dark:text-ink-100 dark:hover:bg-ink-700/40 disabled:opacity-50',
  subtle:
    'rounded-md bg-cream-200 hover:bg-cream-300 text-ink-900 ' +
    'dark:bg-ink-700/40 dark:text-ink-100 dark:hover:bg-ink-700/60 disabled:opacity-50',
  danger:
    'rounded-md bg-oxblood hover:bg-oxblood-700 text-cream-50 shadow-card disabled:opacity-50',
};

const sizeClass: Record<Size, string> = {
  sm: 'h-8  px-3   text-xs',
  md: 'h-10 px-4   text-sm',
  lg: 'h-12 px-6   text-base',
};

function Spinner() {
  return (
    <svg
      className="h-4 w-4 animate-spin"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="9" className="opacity-25" />
      <path d="M21 12a9 9 0 0 1-9 9" strokeLinecap="round" />
    </svg>
  );
}

export const Button = forwardRef<HTMLButtonElement, Props>(
  (
    {
      className,
      variant = 'primary',
      size = 'md',
      loading = false,
      leftIcon,
      rightIcon,
      disabled,
      children,
      type = 'button',
      ...rest
    },
    ref,
  ) => (
    <button
      ref={ref}
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(base, variantClass[variant], sizeClass[size], className)}
      {...rest}
    >
      {loading ? <Spinner /> : leftIcon}
      {children}
      {!loading && rightIcon}
    </button>
  ),
);
Button.displayName = 'Button';
