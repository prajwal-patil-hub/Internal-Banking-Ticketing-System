import { describe, expect, it } from 'vitest';

import { abstainMessage, formatBytes } from './api';

describe('abstainMessage', () => {
  it('explains every reason the service can actually return', () => {
    // Kept in step with KBAnswer.abstain_reason in kb_retrieval_service.py.
    // A reason with no message falls through to the generic text, which reads
    // as a broken feature rather than an honest refusal.
    const reasons = [
      'no_passages',
      'model_insufficient_context',
      'no_valid_citations',
      'low_confidence',
      'model_unavailable',
      'kb_disabled',
    ];
    const generic = abstainMessage('something-unmapped');
    for (const reason of reasons) {
      expect(abstainMessage(reason), reason).not.toBe(generic);
      expect(abstainMessage(reason).length).toBeGreaterThan(20);
    }
  });

  it('tells the user what to do next, not just that it failed', () => {
    expect(abstainMessage('no_passages')).toMatch(/administrator|wording/i);
    expect(abstainMessage('low_confidence')).toMatch(/source document/i);
    expect(abstainMessage('model_unavailable')).toMatch(/try again/i);
  });

  it('never blames the user for a system fault', () => {
    expect(abstainMessage('model_unavailable')).not.toMatch(/your (question|fault)/i);
  });

  it('falls back to a sentence rather than an empty string', () => {
    expect(abstainMessage(null)).toMatch(/grounded/i);
    expect(abstainMessage('brand-new-reason')).toMatch(/grounded/i);
  });

  it('says a discarded answer was discarded, not that nothing was found', () => {
    // These two are different failures and an operator triaging them needs to
    // be able to tell them apart: one means "upload the document", the other
    // means "the model fabricated its sources".
    expect(abstainMessage('no_valid_citations')).toMatch(/discarded/i);
    expect(abstainMessage('no_passages')).not.toMatch(/discarded/i);
  });
});

describe('formatBytes', () => {
  it('scales the unit to the size', () => {
    expect(formatBytes(512)).toBe('512 B');
    expect(formatBytes(2048)).toBe('2 KB');
    expect(formatBytes(5 * 1024 * 1024)).toBe('5.0 MB');
  });

  it('handles the boundaries without switching unit early', () => {
    expect(formatBytes(1023)).toBe('1023 B');
    expect(formatBytes(1024)).toBe('1 KB');
    expect(formatBytes(1024 * 1024 - 1)).toMatch(/KB$/);
    expect(formatBytes(1024 * 1024)).toBe('1.0 MB');
  });

  it('does not render an empty file as blank', () => {
    expect(formatBytes(0)).toBe('0 B');
  });
});
