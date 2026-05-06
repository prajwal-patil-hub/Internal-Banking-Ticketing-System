import { forwardRef } from 'react';
import { cn } from '@/lib/cn';

type Variant = 'primary' | 'ghost' | 'danger';

interface Props extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
}

const variantClass: Record<Variant, string> = {
  primary: 'btn-primary',
  ghost:   'btn-ghost',
  danger:  'inline-flex items-center justify-center gap-2 rounded-xl bg-red-600 hover:bg-red-500 text-white px-4 py-2 text-sm font-medium shadow-card transition-colors disabled:opacity-50',
};

export const Button = forwardRef<HTMLButtonElement, Props>(
  ({ className, variant = 'primary', ...rest }, ref) => (
    <button ref={ref} className={cn(variantClass[variant], className)} {...rest} />
  ),
);
Button.displayName = 'Button';
