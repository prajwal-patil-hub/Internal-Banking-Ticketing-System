import { useState } from 'react';
import { Button } from '@/components/Button';

/**
 * The one and only display of a user's recovery codes.
 *
 * Only hashes are stored, so this cannot be shown again — which is what makes
 * storing them safe, and why the copy insists on saving them now rather than
 * offering a "view later" that could not work.
 */
export function BackupCodes({ codes, onDone }: { codes: string[]; onDone?: () => void }) {
  const [copied, setCopied] = useState(false);

  const asText = codes.join('\n');

  const copy = async () => {
    await navigator.clipboard?.writeText(asText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const download = () => {
    const blob = new Blob(
      [
        'SUCCESS Bank — two-factor recovery codes\n',
        'Each code works once. Keep them somewhere safe and private.\n\n',
        asText,
        '\n',
      ],
      { type: 'text/plain' },
    );
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'success-bank-recovery-codes.txt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="w-full max-w-sm flex flex-col gap-3">
      <div className="card-sm !bg-[var(--warn-bg)] p-3">
        <p className="text-sm font-semibold text-[var(--warn)]">Save your recovery codes</p>
        <p className="text-xs text-[var(--tx-2)] mt-1">
          Each code signs you in once if you lose your phone. They cannot be shown
          again — only their hashes are stored.
        </p>
      </div>

      <ul className="grid grid-cols-2 gap-1.5">
        {codes.map((code) => (
          <li
            key={code}
            className="font-mono text-sm text-center py-1.5 rounded-lg bg-[var(--inset)] border border-[var(--line)] tracking-wide text-[var(--tx)]"
          >
            {code}
          </li>
        ))}
      </ul>

      <div className="flex gap-2">
        <Button variant="ghost" onClick={copy} className="flex-1">
          {copied ? 'Copied' : 'Copy all'}
        </Button>
        <Button variant="ghost" onClick={download} className="flex-1">
          Download
        </Button>
      </div>

      {onDone && (
        <Button onClick={onDone}>I have saved them</Button>
      )}
    </div>
  );
}
