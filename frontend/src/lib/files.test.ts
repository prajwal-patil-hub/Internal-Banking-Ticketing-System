import { describe, it, expect } from 'vitest';
import { formatSize, fileGlyph, guessContentType } from './files';

describe('formatSize', () => {
  it('reports bytes below a kilobyte', () => {
    expect(formatSize(0)).toBe('0 B');
    expect(formatSize(512)).toBe('512 B');
  });

  it('switches to KB and then MB', () => {
    expect(formatSize(2048)).toBe('2 KB');
    expect(formatSize(1_468_006)).toBe('1.4 MB');
  });

  it('matches the server limit exactly at 15 MB', () => {
    // The upload hint and the rejection message both render this number, and
    // they have to agree with the API's own limit or the two disagree on
    // screen.
    expect(formatSize(15 * 1024 * 1024)).toBe('15.0 MB');
  });
});

describe('fileGlyph', () => {
  it('distinguishes the families a ticket actually carries', () => {
    const image = fileGlyph('image/png');
    const pdf = fileGlyph('application/pdf');
    const sheet = fileGlyph('text/csv');

    const paths = new Set([image.path, pdf.path, sheet.path]);
    expect(paths.size).toBe(3);
  });

  it('treats every spreadsheet flavour as a spreadsheet', () => {
    const csv = fileGlyph('text/csv');
    const xlsx = fileGlyph(
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    );
    const xls = fileGlyph('application/vnd.ms-excel');

    expect(xlsx.path).toBe(csv.path);
    expect(xls.path).toBe(csv.path);
  });

  it('falls back rather than throwing on an unknown type', () => {
    const unknown = fileGlyph('application/x-unheard-of');

    expect(unknown.path).toBeTruthy();
    expect(unknown.tone).toBeTruthy();
  });

  it('handles an empty content type', () => {
    expect(() => fileGlyph('')).not.toThrow();
  });
});

describe('guessContentType', () => {
  const file = (name: string, type = '') =>
    new File(['x'], name, { type });

  it('trusts the browser when it knows', () => {
    expect(guessContentType(file('a.png', 'image/png'))).toBe('image/png');
  });

  it('falls back to the extension when the browser says nothing', () => {
    // Real browsers leave `type` empty for plenty of ordinary files; without
    // this fallback a .csv picked on such a machine looks like an unknown
    // type and is rejected before it is sent.
    expect(guessContentType(file('report.csv'))).toBe('text/csv');
    expect(guessContentType(file('statement.PDF'))).toBe('application/pdf');
  });

  it('returns empty for an extension we do not accept', () => {
    expect(guessContentType(file('payload.exe'))).toBe('');
  });

  it('does not crash on a file with no extension', () => {
    expect(guessContentType(file('README'))).toBe('');
  });
});
