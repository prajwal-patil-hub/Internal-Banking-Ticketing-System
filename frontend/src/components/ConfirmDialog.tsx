import { AlertTriangle } from 'lucide-react';

import { Modal } from '@/components/Modal';

interface Props {
  open: boolean;
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  tone?: 'danger' | 'primary';
  onConfirm: () => void;
  onClose: () => void;
  pending?: boolean;
}

/**
 * Glass confirmation dialog. Replaces the native window.confirm calls
 * for destructive actions (deactivate user, deactivate branch, reset
 * password, etc.) with a polished modal.
 */
export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  tone = 'danger',
  onConfirm,
  onClose,
  pending,
}: Props) {
  return (
    <Modal open={open} onClose={onClose} title={title} description={description}>
      <div className="flex items-start gap-4">
        <span
          className={`h-10 w-10 rounded-2xl grid place-items-center shrink-0 ${
            tone === 'danger' ? 'bg-danger-soft text-danger-deep' : 'bg-brand-50 text-brand-700'
          }`}
        >
          <AlertTriangle className="h-5 w-5" />
        </span>
        <div className="text-sm text-ink-muted leading-relaxed flex-1">
          This action will be recorded in the audit log and cannot be silently undone.
          Continue?
        </div>
      </div>
      <div className="flex justify-end gap-2 mt-6">
        <button onClick={onClose} className="btn-secondary" disabled={pending}>
          {cancelLabel}
        </button>
        <button
          onClick={onConfirm}
          className={tone === 'danger' ? 'btn-danger' : 'btn-primary'}
          disabled={pending}
        >
          {pending ? 'Working…' : confirmLabel}
        </button>
      </div>
    </Modal>
  );
}
