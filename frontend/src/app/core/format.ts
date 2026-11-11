import { Colour, FridgeCard } from './models';

/**
 * Card colour, the rule Summer did not spell out (also in NOTES.md):
 *  red   - at least one excursion in the period (ongoing ones get a badge)
 *  amber - no excursion, but a gap or a sensor error: the inspector question has a hole
 *  green - otherwise; isolated door-opening spikes stay green
 *  grey  - no readings at all in the period
 */
export function colourFor(
  c: Pick<FridgeCard, 'excursion_count' | 'gap_count' | 'error_count' | 'last_reading_local'>,
): Colour {
  if (c.excursion_count > 0) return 'red';
  if (c.gap_count > 0 || c.error_count > 0) return 'amber';
  if (!c.last_reading_local) return 'grey';
  return 'green';
}

export const COLOUR_LABEL: Record<Colour, string> = {
  red: 'Above 5°C',
  amber: 'Check data',
  green: 'OK',
  grey: 'No data',
};

/** Pick the logger whose code appears in a filename such as `TL-0512_2026-W38.csv`. */
export function loggerFromFilename(filename: string, codes: readonly string[]): string | null {
  const m = /TL-\d{3,6}/i.exec(filename ?? '');
  if (!m) return null;
  const code = m[0].toUpperCase();
  return codes.includes(code) ? code : null;
}

export function fmtDuration(minutes: number): string {
  if (minutes < 60) return `${minutes} min`;
  const d = Math.floor(minutes / 1440);
  const h = Math.floor((minutes % 1440) / 60);
  const m = minutes % 60;
  const parts: string[] = [];
  if (d) parts.push(`${d} d`);
  if (h) parts.push(`${h} h`);
  if (m && !d) parts.push(`${m} min`);
  return parts.join(' ');
}

export function fmtTemp(t: number | null | undefined): string {
  return t === null || t === undefined ? '—' : `${t.toFixed(1)}°C`;
}

/** ISO date (YYYY-MM-DD) arithmetic, in calendar days, without timezone surprises. */
export function addDays(iso: string, days: number): string {
  const [y, m, d] = iso.split('-').map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d + days));
  return dt.toISOString().slice(0, 10);
}

export function mondayOf(iso: string): string {
  const [y, m, d] = iso.split('-').map(Number);
  const dow = new Date(Date.UTC(y, m - 1, d)).getUTCDay(); // 0 = Sunday
  return addDays(iso, -((dow + 6) % 7));
}

export function weekOf(iso: string): { from: string; to: string } {
  const from = mondayOf(iso);
  return { from, to: addDays(from, 6) };
}
