import { pickDroppedFile } from './drop';

const f = (name: string) => new File(['x'], name);

describe('pickDroppedFile', () => {
  it('takes a single logger export as is', () => {
    expect(pickDroppedFile([f('TL-0231_2026-W39.csv')])).toEqual({
      file: expect.objectContaining({ name: 'TL-0231_2026-W39.csv' }),
      notice: null,
    });
  });

  it('accepts .txt and .tsv exports, any case', () => {
    expect(pickDroppedFile([f('export.TXT')]).file?.name).toBe('export.TXT');
    expect(pickDroppedFile([f('export.tsv')]).file?.name).toBe('export.tsv');
  });

  it('refuses files that are not logger exports', () => {
    const r = pickDroppedFile([f('photo.jpg')]);
    expect(r.file).toBeNull();
    expect(r.notice).toContain('photo.jpg is not a logger export');
  });

  it('uses the first export when several files are dropped, and says so', () => {
    const r = pickDroppedFile([f('notes.pdf'), f('TL-0512.csv'), f('TL-0417.csv')]);
    expect(r.file?.name).toBe('TL-0512.csv');
    expect(r.notice).toContain('One file at a time');
  });

  it('does nothing for an empty drop', () => {
    expect(pickDroppedFile([])).toEqual({ file: null, notice: null });
    expect(pickDroppedFile(null)).toEqual({ file: null, notice: null });
  });
});
