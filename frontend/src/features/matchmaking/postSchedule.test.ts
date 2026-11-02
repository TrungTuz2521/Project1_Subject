import { describe, expect, it } from 'vitest';
import { postEnd, postStartOptions, vietnamDate } from './postSchedule';

describe('opponent post time choices match backend schedule', () => {
  const now = new Date('2026-11-02T08:00:00Z'); // 15:00 Vietnam
  it('offers only the 90-minute starts and never allows an end after closing', () => {
    expect(postStartOptions('2026-11-03', now)).toEqual(['06:00', '07:30', '09:00', '10:30', '12:00', '13:30', '15:00', '16:30', '18:00', '19:30', '21:00']);
    expect(postEnd('2026-11-03T21:00')).toBe('2026-11-03T22:30');
    expect(postEnd('2026-11-03T15:00')).toBe('2026-11-03T16:30');
  });
  it('excludes a slot starting now, past dates and dates beyond ten days', () => {
    expect(postStartOptions('2026-11-02', now)).toEqual(['16:30', '18:00', '19:30', '21:00']);
    expect(postStartOptions('2026-11-01', now)).toEqual([]);
    expect(postStartOptions('2026-11-12', now)).toHaveLength(11);
    expect(postStartOptions('2026-11-13', now)).toEqual([]);
    expect(postStartOptions('', now)).toEqual([]);
  });
  it('uses the Vietnam calendar date at UTC midnight boundaries and handles a day with no slots left', () => {
    const late = new Date('2026-11-02T16:30:00Z'); // 23:30 Vietnam
    expect(postStartOptions('2026-11-02', late)).toEqual([]);
    expect(vietnamDate(new Date('2026-11-02T18:00:00Z'))).toBe('2026-11-03');
    expect(postEnd('')).toBe('');
  });
});
