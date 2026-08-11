import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mocked at the module boundary so these tests exercise the orchestration —
// ordering, per-file outcomes, progress — without a network or a server.
vi.mock('@/lib/api', () => ({
  api: { post: vi.fn(), get: vi.fn(), delete: vi.fn() },
  AI_TIMEOUT_MS: 190_000,
  extractError: (e: unknown) => ({
    message: (e as { message?: string })?.message ?? 'Request failed',
  }),
}));

import { api } from '@/lib/api';
import { uploadAttachments, MAX_ATTACHMENT_BYTES, ATTACHMENT_ACCEPT } from './api';

const post = api.post as unknown as ReturnType<typeof vi.fn>;

const file = (name: string) => new File(['x'], name, { type: 'application/pdf' });
const okResponse = { data: { data: { id: 'a1', filename: 'x' } } };

beforeEach(() => {
  post.mockReset();
});

describe('uploadAttachments', () => {
  it('reports success for every file', async () => {
    post.mockResolvedValue(okResponse);

    const results = await uploadAttachments('t1', [file('a.pdf'), file('b.pdf')]);

    expect(results.map((r) => r.ok)).toEqual([true, true]);
    expect(post).toHaveBeenCalledTimes(2);
  });

  it('keeps going after one file fails, and names the one that did', async () => {
    post
      .mockResolvedValueOnce(okResponse)
      .mockRejectedValueOnce(new Error('storage unavailable'))
      .mockResolvedValueOnce(okResponse);

    const results = await uploadAttachments('t1', [
      file('first.pdf'),
      file('broken.pdf'),
      file('third.pdf'),
    ]);

    // Abandoning the rest on the first failure would lose files the user
    // already chose, for a reason unrelated to them.
    expect(results.map((r) => r.ok)).toEqual([true, false, true]);
    const failed = results.find((r) => !r.ok);
    expect(failed?.file.name).toBe('broken.pdf');
    expect(failed?.error).toContain('storage unavailable');
  });

  it('uploads one at a time rather than all at once', async () => {
    let inFlight = 0;
    let peak = 0;
    post.mockImplementation(async () => {
      peak = Math.max(peak, ++inFlight);
      await new Promise((r) => setTimeout(r, 5));
      inFlight--;
      return okResponse;
    });

    await uploadAttachments('t1', [file('a.pdf'), file('b.pdf'), file('c.pdf')]);

    // Five screenshots should not open five concurrent multipart requests.
    expect(peak).toBe(1);
  });

  it('reports progress after each file', async () => {
    post.mockResolvedValue(okResponse);
    const seen: Array<[number, number]> = [];

    await uploadAttachments('t1', [file('a.pdf'), file('b.pdf')], {
      onProgress: (done, total) => seen.push([done, total]),
    });

    expect(seen).toEqual([[1, 2], [2, 2]]);
  });

  it('reports progress for a failed file too', async () => {
    post.mockRejectedValue(new Error('nope'));
    const seen: Array<[number, number]> = [];

    await uploadAttachments('t1', [file('a.pdf')], {
      onProgress: (done, total) => seen.push([done, total]),
    });

    // Otherwise the "Uploading file 1 of 2…" line stalls forever on a failure.
    expect(seen).toEqual([[1, 1]]);
  });

  it('attaches to a reply when given a comment id', async () => {
    post.mockResolvedValue(okResponse);

    await uploadAttachments('t1', [file('fix.pdf')], { commentId: 'c9' });

    expect(post.mock.calls[0][2]).toMatchObject({ params: { comment_id: 'c9' } });
  });

  it('sends no comment id when attaching to the ticket itself', async () => {
    post.mockResolvedValue(okResponse);

    await uploadAttachments('t1', [file('evidence.pdf')]);

    expect(post.mock.calls[0][2]?.params).toBeUndefined();
  });

  it('does nothing when there are no files', async () => {
    const results = await uploadAttachments('t1', []);

    expect(results).toEqual([]);
    expect(post).not.toHaveBeenCalled();
  });

  it('allows longer than the default timeout', async () => {
    post.mockResolvedValue(okResponse);

    await uploadAttachments('t1', [file('big.pdf')]);

    // A 15 MB file on a slow link will not finish inside the 15s default.
    expect(post.mock.calls[0][2]?.timeout).toBeGreaterThanOrEqual(60_000);
  });
});

describe('attachment constants', () => {
  it('matches the server limit of 15 MB', () => {
    expect(MAX_ATTACHMENT_BYTES).toBe(15 * 1024 * 1024);
  });

  it('offers no executable or archive types', () => {
    for (const banned of ['.exe', '.zip', '.sh', '.js']) {
      expect(ATTACHMENT_ACCEPT).not.toContain(banned);
    }
  });
});
