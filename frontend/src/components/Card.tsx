import { motion, type HTMLMotionProps } from 'framer-motion';
import { cn } from '@/lib/cn';

type Variant = 'glass' | 'plain';

interface Props extends Omit<HTMLMotionProps<'div'>, 'ref'> {
  padded?: boolean;
  variant?: Variant;
  hover?: boolean;
}

/**
 * Glassmorphic surface primitive. Default = `glass` (blurred, translucent),
 * `plain` for tightly nested sub-surfaces that shouldn't compound blur.
 */
export function Card({
  className,
  padded = true,
  variant = 'glass',
  hover = false,
  children,
  ...rest
}: Props) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
      whileHover={hover ? { y: -2 } : undefined}
      className={cn(
        'rounded-4xl text-ink',
        variant === 'glass' ? 'glass' : 'bg-white/60 border border-white/40',
        padded && 'p-6',
        hover && 'hover:shadow-glassLg transition-shadow duration-300',
        className,
      )}
      {...rest}
    >
      {children}
    </motion.div>
  );
}
