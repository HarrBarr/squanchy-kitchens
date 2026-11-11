import {
  addDays,
  cardLabel,
  colourFor,
  incompletePeriod,
  fmtDuration,
  loggerFromFilename,
  mondayOf,
  weekOf,
} from './format';

const base = {
  excursion_count: 0,
  gap_count: 0,
  error_count: 0,
  last_reading_local: '2026-09-20T23:45:00',
};

describe('colourFor', () => {
  it('is red when the period has an excursion, whatever else happened', () => {
    expect(colourFor({ ...base, excursion_count: 1, gap_count: 2, error_count: 3 })).toBe('red');
  });
  it('is amber for a gap without an excursion (Beit Shemesh)', () => {
    expect(colourFor({ ...base, gap_count: 1 })).toBe('amber');
  });
  it('is amber for sensor errors without an excursion (Haifa)', () => {
    expect(colourFor({ ...base, error_count: 4 })).toBe('amber');
  });
  it('is green otherwise, spikes included (they are not in the summary counts)', () => {
    expect(colourFor(base)).toBe('green');
  });
  it('stays red when still above the limit at the last uploaded reading', () => {
    expect(colourFor({ ...base, last_reading_local: null, still_above: true })).toBe('red');
  });
  it('is grey with no readings', () => {
    expect(colourFor({ ...base, last_reading_local: null })).toBe('grey');
  });
});

describe('loggerFromFilename', () => {
  const codes = ['TL-0231', 'TL-0512'];
  it('finds a registered code', () => {
    expect(loggerFromFilename('TL-0512_2026-W38.csv', codes)).toBe('TL-0512');
    expect(loggerFromFilename('export tl-0231 week38.csv', codes)).toBe('TL-0231');
  });
  it('returns null for unknown or missing codes', () => {
    expect(loggerFromFilename('TL-9999_2026-W38.csv', codes)).toBeNull();
    expect(loggerFromFilename('fridge.csv', codes)).toBeNull();
  });
});

describe('fmtDuration', () => {
  it('formats minutes, hours and days', () => {
    expect(fmtDuration(60)).toBe('1 h');
    expect(fmtDuration(135)).toBe('2 h 15 min');
    expect(fmtDuration(9690)).toBe('6 d 17 h');
    expect(fmtDuration(15)).toBe('15 min');
  });
});

describe('week helpers', () => {
  it('finds the Monday of ISO week 38', () => {
    expect(mondayOf('2026-09-20')).toBe('2026-09-14');
    expect(mondayOf('2026-09-14')).toBe('2026-09-14');
    expect(weekOf('2026-09-17')).toEqual({ from: '2026-09-14', to: '2026-09-20' });
    expect(addDays('2026-09-14', -7)).toBe('2026-09-07');
  });
});

describe('incomplete week', () => {
  it('is incomplete when only some fridges have readings', () => {
    expect(incompletePeriod({ fridges_total: 31, fridges_with_readings: 1 })).toBe(true);
    expect(incompletePeriod({ fridges_total: 31, fridges_with_readings: 31 })).toBe(false);
    expect(incompletePeriod({ fridges_total: 31, fridges_with_readings: 0 })).toBe(false);
  });
  it('labels a waiting fridge "Awaiting upload", not "No data"', () => {
    expect(cardLabel({ awaiting_upload: true }, 'grey')).toBe('Awaiting upload');
    expect(cardLabel({ awaiting_upload: false }, 'grey')).toBe('No data');
    expect(cardLabel({ awaiting_upload: false }, 'red')).toBe('Above 5°C');
  });
});
