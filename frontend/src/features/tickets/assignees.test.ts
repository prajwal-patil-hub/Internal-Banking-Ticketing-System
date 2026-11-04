import { describe, expect, it } from 'vitest';
import { leaveLabel, rankCandidates } from './assignees';
import type { WorkloadEntry } from './api';

function entry(over: Partial<WorkloadEntry> = {}): WorkloadEntry {
  return {
    user_id: over.user_id ?? Math.random().toString(36).slice(2),
    email: 'a@bank.local',
    full_name: 'A Person',
    role: 'agent',
    open_count: 0,
    on_leave: false,
    leave_from: null,
    leave_to: null,
    leave_note: null,
    ...over,
  };
}

describe('rankCandidates', () => {
  it('puts the lightest queue first', () => {
    const ranked = rankCandidates([
      entry({ user_id: 'busy', open_count: 9 }),
      entry({ user_id: 'idle', open_count: 1 }),
      entry({ user_id: 'mid', open_count: 4 }),
    ]);
    expect(ranked.map((e) => e.user_id)).toEqual(['idle', 'mid', 'busy']);
  });

  it('sinks everyone on leave below everyone available, however light their queue', () => {
    // The whole point: the top entry is what a supervisor clicks without
    // reading. Someone away with zero open tickets must never sit there.
    const ranked = rankCandidates([
      entry({ user_id: 'away', open_count: 0, on_leave: true }),
      entry({ user_id: 'here', open_count: 7 }),
    ]);
    expect(ranked.map((e) => e.user_id)).toEqual(['here', 'away']);
  });

  it('still orders the away group by queue length', () => {
    const ranked = rankCandidates([
      entry({ user_id: 'away-busy', open_count: 5, on_leave: true }),
      entry({ user_id: 'away-idle', open_count: 2, on_leave: true }),
    ]);
    expect(ranked.map((e) => e.user_id)).toEqual(['away-idle', 'away-busy']);
  });

  it('does not mutate the array it was given', () => {
    const input = [entry({ user_id: 'b', open_count: 5 }), entry({ user_id: 'a', open_count: 1 })];
    const before = input.map((e) => e.user_id);
    rankCandidates(input);
    expect(input.map((e) => e.user_id)).toEqual(before);
  });
});

describe('leaveLabel', () => {
  it('says nothing for someone who is available', () => {
    expect(leaveLabel(entry())).toBeNull();
  });

  it('gives the return date when there is one', () => {
    expect(leaveLabel(entry({ on_leave: true, leave_to: '2026-08-25' })))
      .toBe('on leave until 2026-08-25');
  });

  it('does not invent a return date for indefinite leave', () => {
    expect(leaveLabel(entry({ on_leave: true, leave_to: null }))).toBe('on leave');
  });
});
