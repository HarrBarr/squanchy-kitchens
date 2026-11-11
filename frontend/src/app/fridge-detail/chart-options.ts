import type { EChartsCoreOption } from 'echarts/core';
import { Series } from '../core/models';

const RED = '#c92a2a';
const ORANGE = '#e8590c';
const GREY = '#868e96';
const LINE = '#1b6e7a';

function t(s: string): number {
  // ts_local has no offset: parsed as browser-local wall clock and shown the same way,
  // so the axis reads in Asia/Jerusalem time whatever the viewer's timezone.
  return new Date(s).getTime();
}

/**
 * Build the fridge chart. The line never crosses a gap or a sensor error: a null point is
 * inserted there, and connectNulls is off. Gaps are grey bands, excursions red bands, the
 * 5°C limit a dashed line, spikes orange triangles, sensor errors grey crosses.
 */
export function buildChartOptions(s: Series): EChartsCoreOption {
  const stepMs = s.sample_interval_minutes * 60_000;
  const line: [number, number | null][] = [];
  const errs: [number, number][] = [];
  let prev: number | null = null;

  const temps = s.readings.filter((r) => r.temp_c !== null).map((r) => r.temp_c as number);
  const yMin = Math.floor(Math.min(s.threshold_c - 3, ...temps) - 0.5);
  const yMax = Math.ceil(Math.max(s.threshold_c + 2, ...temps) + 0.5);

  for (const r of s.readings) {
    const x = t(r.ts_local);
    if (prev !== null && x - prev > stepMs) line.push([prev + stepMs / 2, null]);
    if (r.status === 'err' || r.temp_c === null) {
      line.push([x, null]);
      errs.push([x, yMin + 0.3]);
    } else {
      line.push([x, r.temp_c]);
    }
    prev = x;
  }

  const bands = [
    ...s.excursions.map((e) => [
      {
        xAxis: t(e.start_local),
        itemStyle: { color: 'rgba(201, 42, 42, 0.12)' },
        name: `Excursion · peak ${e.peak_c.toFixed(1)}°C`,
      },
      { xAxis: t(e.end_local) },
    ]),
    ...s.gaps.map((g) => [
      {
        xAxis: t(g.start_local),
        itemStyle: { color: 'rgba(134, 142, 150, 0.22)' },
        name: 'No data',
      },
      { xAxis: t(g.end_local) },
    ]),
  ];

  return {
    animation: false,
    grid: { left: 44, right: 16, top: 24, bottom: 72 },
    tooltip: {
      trigger: 'axis',
      valueFormatter: (v: unknown) => (typeof v === 'number' ? `${v.toFixed(1)}°C` : 'no reading'),
    },
    legend: { bottom: 0, data: ['Temperature', 'Spike', 'Sensor error'] },
    xAxis: {
      type: 'time',
      min: t(`${s.period_from}T00:00:00`),
      max: t(`${s.period_to}T23:59:59`),
      axisLabel: { hideOverlap: true },
    },
    yAxis: {
      type: 'value',
      min: yMin,
      max: yMax,
      axisLabel: { formatter: '{value}°' },
    },
    dataZoom: [
      { type: 'inside', filterMode: 'none' },
      { type: 'slider', height: 18, bottom: 30, filterMode: 'none' },
    ],
    series: [
      {
        name: 'Temperature',
        type: 'line',
        data: line,
        showSymbol: false,
        connectNulls: false,
        lineStyle: { width: 1.6, color: LINE },
        itemStyle: { color: LINE },
        markLine: {
          silent: true,
          symbol: 'none',
          lineStyle: { type: 'dashed', color: RED, width: 1.5 },
          label: { formatter: `${s.threshold_c}°C limit`, position: 'insideEndTop', color: RED },
          data: [{ yAxis: s.threshold_c }],
        },
        markArea: { silent: false, label: { show: false }, data: bands },
      },
      {
        name: 'Spike',
        type: 'scatter',
        data: s.spikes.map((p) => [t(p.ts_local), p.temp_c]),
        symbol: 'triangle',
        symbolSize: 11,
        itemStyle: { color: ORANGE },
        z: 5,
      },
      {
        name: 'Sensor error',
        type: 'scatter',
        data: errs,
        symbol: 'path://M2,2 L8,8 M8,2 L2,8',
        symbolSize: 9,
        itemStyle: { color: GREY, borderColor: GREY, borderWidth: 2 },
        tooltip: { valueFormatter: () => 'ERR' },
      },
    ],
  };
}
