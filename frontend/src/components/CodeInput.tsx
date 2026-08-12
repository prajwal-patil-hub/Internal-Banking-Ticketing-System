import { useRef, type ClipboardEvent, type KeyboardEvent } from 'react';
import { cn } from '@/lib/cn';

/**
 * Segmented six-digit code entry.
 *
 * One real input per digit rather than a single field styled with letter
 * spacing: the boxes make the expected length obvious, and each digit gets its
 * own caret position so correcting the third digit does not mean retyping the
 * rest. Paste is handled on any box, because people paste the whole code.
 */
export function CodeInput({
  value, onChange, length = 6, onComplete, disabled, autoFocus,
}: {
  value: string;
  onChange: (next: string) => void;
  length?: number;
  /** Fires once the last digit lands — lets the form submit itself. */
  onComplete?: (code: string) => void;
  disabled?: boolean;
  autoFocus?: boolean;
}) {
  const refs = useRef<Array<HTMLInputElement | null>>([]);
  const digits = value.padEnd(length, ' ').slice(0, length).split('');

  const commit = (next: string) => {
    const cleaned = next.replace(/\D/g, '').slice(0, length);
    onChange(cleaned);
    if (cleaned.length === length) onComplete?.(cleaned);
    return cleaned;
  };

  const handleDigit = (index: number, raw: string) => {
    const digit = raw.replace(/\D/g, '').slice(-1);
    if (!digit) return;

    const chars = value.padEnd(length, ' ').split('');
    chars[index] = digit;
    const cleaned = commit(chars.join('').replace(/ /g, ''));

    // Advance while there is somewhere to advance to.
    if (index < length - 1) refs.current[index + 1]?.focus();
    else if (cleaned.length === length) refs.current[index]?.blur();
  };

  const handleKeyDown = (index: number, e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Backspace') {
      e.preventDefault();
      const chars = value.split('');
      if (chars[index]) {
        // Clear this box first; only step back once it is already empty, which
        // is what people expect from a segmented field.
        chars.splice(index, 1);
        commit(chars.join(''));
      } else if (index > 0) {
        const prev = value.split('');
        prev.splice(index - 1, 1);
        commit(prev.join(''));
        refs.current[index - 1]?.focus();
      }
    } else if (e.key === 'ArrowLeft' && index > 0) {
      e.preventDefault();
      refs.current[index - 1]?.focus();
    } else if (e.key === 'ArrowRight' && index < length - 1) {
      e.preventDefault();
      refs.current[index + 1]?.focus();
    }
  };

  const handlePaste = (e: ClipboardEvent<HTMLInputElement>) => {
    e.preventDefault();
    const pasted = commit(e.clipboardData.getData('text'));
    refs.current[Math.min(pasted.length, length - 1)]?.focus();
  };

  return (
    <div className="flex gap-2" role="group" aria-label={`${length}-digit authentication code`}>
      {digits.map((digit, i) => (
        <input
          key={i}
          ref={(el) => { refs.current[i] = el; }}
          value={digit.trim()}
          onChange={(e) => handleDigit(i, e.target.value)}
          onKeyDown={(e) => handleKeyDown(i, e)}
          onPaste={handlePaste}
          onFocus={(e) => e.target.select()}
          disabled={disabled}
          inputMode="numeric"
          autoComplete={i === 0 ? 'one-time-code' : 'off'}
          maxLength={1}
          aria-label={`Digit ${i + 1}`}
          autoFocus={autoFocus && i === 0}
          className={cn(
            'h-14 w-12 rounded-xl text-center text-2xl font-semibold tabular-nums',
            'border border-[var(--line)] bg-[var(--bg)] text-[var(--tx)]',
            'outline-none transition-colors',
            'focus:border-[var(--brand)] focus:ring-2 focus:ring-[var(--brand)]/20',
            'disabled:opacity-50',
            digit.trim() && 'border-[var(--brand)]',
          )}
        />
      ))}
    </div>
  );
}
