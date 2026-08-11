import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { FileStager } from './FileStager';
import { MAX_ATTACHMENT_BYTES } from '@/features/tickets/api';

/** A File of a given size without allocating that many bytes. */
function fileOf(name: string, bytes: number, type = 'application/pdf'): File {
  const file = new File(['x'], name, { type });
  Object.defineProperty(file, 'size', { value: bytes });
  return file;
}

/** Wraps the controlled component so tests can drive it as the page does. */
function Harness({ onChange }: { onChange?: (f: File[]) => void } = {}) {
  const [files, setFiles] = useState<File[]>([]);
  return (
    <FileStager
      files={files}
      onChange={(next) => {
        setFiles(next);
        onChange?.(next);
      }}
    />
  );
}

// The real input is hidden and opened by the visible "Choose files" button, so
// it has no accessible name to query by. Tests drive it directly, which is what
// clicking that button does anyway.
const picker = () =>
  document.querySelector('input[type="file"]') as HTMLInputElement;

describe('FileStager', () => {
  it('lists a chosen file with its size', async () => {
    render(<Harness />);

    await userEvent.upload(picker(), fileOf('statement.pdf', 2048));

    expect(screen.getByText('statement.pdf')).toBeInTheDocument();
    expect(screen.getByText('2 KB')).toBeInTheDocument();
  });

  it('accepts several files at once', async () => {
    render(<Harness />);

    await userEvent.upload(picker(), [
      fileOf('one.pdf', 100),
      fileOf('two.png', 200, 'image/png'),
    ]);

    expect(screen.getByText('one.pdf')).toBeInTheDocument();
    expect(screen.getByText('two.png')).toBeInTheDocument();
  });

  it('refuses a file over the limit and says what the limit is', async () => {
    render(<Harness />);

    await userEvent.upload(picker(), fileOf('huge.pdf', MAX_ATTACHMENT_BYTES + 1));

    // Rejected before any upload is attempted, and the message names both the
    // offending file and the cap rather than just saying "too large".
    expect(screen.queryByText('huge.pdf')).not.toBeInTheDocument();
    const error = screen.getByText(/^Too large/);
    expect(error).toHaveTextContent('15.0 MB');
    expect(error).toHaveTextContent('huge.pdf');
  });

  it('accepts a file exactly on the limit', async () => {
    render(<Harness />);

    await userEvent.upload(picker(), fileOf('exact.pdf', MAX_ATTACHMENT_BYTES));

    expect(screen.getByText('exact.pdf')).toBeInTheDocument();
  });

  it('keeps the good files when one in the batch is too large', async () => {
    render(<Harness />);

    await userEvent.upload(picker(), [
      fileOf('fine.pdf', 1024),
      fileOf('huge.pdf', MAX_ATTACHMENT_BYTES + 1),
    ]);

    // Dropping the whole selection because one file was oversized would make
    // the user re-pick the others for no reason.
    expect(screen.getByText('fine.pdf')).toBeInTheDocument();
    expect(screen.queryByText('huge.pdf')).not.toBeInTheDocument();
  });

  it('ignores the same file chosen twice', async () => {
    render(<Harness />);

    await userEvent.upload(picker(), fileOf('same.pdf', 500));
    await userEvent.upload(picker(), fileOf('same.pdf', 500));

    // Same name and size is a double-click, not two documents.
    expect(screen.getAllByText('same.pdf')).toHaveLength(1);
  });

  it('treats same name but different size as a different file', async () => {
    render(<Harness />);

    await userEvent.upload(picker(), fileOf('report.pdf', 500));
    await userEvent.upload(picker(), fileOf('report.pdf', 900));

    expect(screen.getAllByText('report.pdf')).toHaveLength(2);
  });

  it('removes a staged file', async () => {
    render(<Harness />);
    await userEvent.upload(picker(), fileOf('remove-me.pdf', 100));

    await userEvent.click(screen.getByRole('button', { name: /Remove remove-me\.pdf/ }));

    expect(screen.queryByText('remove-me.pdf')).not.toBeInTheDocument();
  });

  it('hands the files back to the page', async () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);

    await userEvent.upload(picker(), fileOf('sent-up.pdf', 100));

    // The component owns no network code; the page uploads what it receives.
    expect(onChange).toHaveBeenCalledOnce();
    expect(onChange.mock.calls[0][0][0].name).toBe('sent-up.pdf');
  });

  it('disables the control while an upload is in flight', () => {
    render(<FileStager files={[]} onChange={() => {}} disabled />);

    expect(screen.getByRole('button', { name: /Choose files/i })).toBeDisabled();
  });

  it('offers the accepted types to the file picker', () => {
    render(<Harness />);

    const accept = picker().getAttribute('accept') ?? '';
    expect(accept).toContain('image/*');
    expect(accept).toContain('.pdf');
    expect(accept).toContain('.xlsx');
    // Executables and archives are refused server-side; not offering them
    // avoids a rejection the user could not have predicted.
    expect(accept).not.toContain('.exe');
    expect(accept).not.toContain('.zip');
  });
});
