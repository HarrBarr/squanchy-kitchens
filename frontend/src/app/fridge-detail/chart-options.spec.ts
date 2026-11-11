import { Series } from '../core/models';
import { buildChartOptions } from './chart-options';

function series(partial: Partial<Series>): Series {
  return {
    fridge_id: 1,
    branch: 'Jerusalem',
    fridge: 'Dairy',
    period_from: '2026-09-14',
    period_to: '2026-09-20',
    period_label: '2026-W38',
    threshold_c: 5,
    sample_interval_minutes: 15,
    readings: [],
    gaps: [],
    excursions: [],
    spikes: [],
    ...partial,
  };
}

const r = (ts: string, temp: number | null) => ({
  ts_local: ts,
  temp_c: temp,
  status: temp === null ? ('err' as const) : ('ok' as const),
  raw_value: temp === null ? 'ERR' : String(temp),
  logger: 'TL-0512',
});

describe('buildChartOptions', () => {
  it('breaks the line across a gap instead of drawing through it', () => {
    const opts = buildChartOptions(
      series({ readings: [r('2026-09-14T06:15:00', 3.9), r('2026-09-14T08:30:00', 4.0)] }),
    ) as { series: { data: [number, number | null][] }[] };
    const data = opts.series[0].data;
    expect(data.length).toBe(3);
    expect(data[1][1]).toBeNull();
  });

  it('turns ERR into a null point and a sensor-error marker', () => {
    const opts = buildChartOptions(
      series({ readings: [r('2026-09-14T06:15:00', 3.9), r('2026-09-14T06:30:00', null)] }),
    ) as { series: { data: unknown[] }[] };
    expect(opts.series[0].data[1]).toEqual([new Date('2026-09-14T06:30:00').getTime(), null]);
    expect(opts.series[2].data.length).toBe(1);
  });
});
