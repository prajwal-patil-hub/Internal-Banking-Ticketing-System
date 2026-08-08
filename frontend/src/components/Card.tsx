import { cn } from '@/lib/cn';

interface Props extends React.HTMLAttributes<HTMLDivElement> {
  padded?: boolean;
  size?: 'sm' | 'md';
}

export function Card({ className, padded = true, size = 'md', ...rest }: Props) {
  return (
    <div
      className={cn(
        size === 'sm' ? 'card-sm' : 'card',
        !padded && '!p-0',
        className,
      )}
      {...rest}
    />
  );
}
