import type { EChartsCoreOption } from 'echarts/core';
import { Series } from '../core/models';

// Simple To Work "Northern lights" palette, on the dark glass panel.
const RED = '#FF5C5C';
const WARN = '#FFC48A';
const MUTED = '#B3BAD6';
const GRID = 'rgba(245, 247, 255, 0.07)';
const AXIS = 'rgba(245, 247, 255, 0.18)';
const MONO = "'JetBrains Mono Variable', 'JetBrains Mono', monospace";
const BODY = "'Inter Variable', 'Inter', system-ui, sans-serif";

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
        itemStyle: { color: 'rgba(255, 92, 92, 0.14)' },
        name: `Excursion · peak ${e.peak_c.toFixed(1)}°C`,
      },
      { xAxis: t(e.end_local) },
    ]),
    ...s.gaps.map((g) => [
      {
        xAxis: t(g.start_local),
        itemStyle: {
          color: 'rgba(245, 247, 255, 0.06)',
          borderColor: 'rgba(245, 247, 255, 0.18)',
          borderType: 'dashed',
          borderWidth: 1,
        },
        name: 'No data',
      },
      { xAxis: t(g.end_local) },
    ]),
  ];

  return {
    animation: false,
    textStyle: { fontFamily: BODY, color: MUTED },
    grid: { left: 48, right: 16, top: 28, bottom: 76 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(14, 17, 38, 0.92)',
      borderColor: 'rgba(245, 247, 255, 0.16)',
      textStyle: { color: '#F5F7FF', fontFamily: BODY },
      axisPointer: { lineStyle: { color: 'rgba(124, 242, 200, 0.5)' } },
      valueFormatter: (v: unknown) => (typeof v === 'number' ? `${v.toFixed(1)}°C` : 'no reading'),
    },
    legend: {
      bottom: 0,
      data: ['Temperature', 'Spike', 'Sensor error'],
      textStyle: { color: MUTED },
      icon: 'roundRect',
      itemWidth: 14,
      itemHeight: 6,
    },
    xAxis: {
      type: 'time',
      min: t(`${s.period_from}T00:00:00`),
      max: t(`${s.period_to}T23:59:59`),
      axisLabel: { hideOverlap: true, color: MUTED, fontFamily: MONO, fontSize: 11 },
      axisLine: { lineStyle: { color: AXIS } },
      axisTick: { lineStyle: { color: AXIS } },
      splitLine: { show: true, lineStyle: { color: GRID } },
    },
    yAxis: {
      type: 'value',
      min: yMin,
      max: yMax,
      axisLabel: { formatter: '{value}°', color: MUTED, fontFamily: MONO, fontSize: 11 },
      splitLine: { lineStyle: { color: GRID } },
    },
    dataZoom: [
      { type: 'inside', filterMode: 'none' },
      {
        type: 'slider',
        height: 18,
        bottom: 32,
        filterMode: 'none',
        borderColor: 'rgba(245, 247, 255, 0.12)',
        backgroundColor: 'rgba(245, 247, 255, 0.03)',
        fillerColor: 'rgba(124, 242, 200, 0.12)',
        dataBackground: {
          lineStyle: { color: 'rgba(124, 242, 200, 0.5)' },
          areaStyle: { color: 'rgba(124, 242, 200, 0.08)' },
        },
        handleStyle: { color: '#7CF2C8', borderColor: '#7CF2C8' },
        moveHandleStyle: { color: 'rgba(124, 242, 200, 0.4)' },
        textStyle: { color: MUTED },
      },
    ],
    series: [
      {
        name: 'Temperature',
        type: 'line',
        data: line,
        showSymbol: false,
        connectNulls: false,
        // Aurora gradient along the line, with a soft glow underneath.
        lineStyle: {
          width: 2,
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 1,
            y2: 0,
            colorStops: [
              { offset: 0, color: '#2FD5FF' },
              { offset: 0.5, color: '#7CF2C8' },
              { offset: 1, color: '#6A5CFF' },
            ],
          },
          shadowColor: 'rgba(124, 242, 200, 0.45)',
          shadowBlur: 10,
        },
        itemStyle: { color: '#7CF2C8' },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(124, 242, 200, 0.18)' },
              { offset: 1, color: 'rgba(124, 242, 200, 0)' },
            ],
          },
        },
        markLine: {
          silent: true,
          symbol: 'none',
          lineStyle: { type: 'dashed', color: RED, width: 1.5 },
          label: {
            formatter: `${s.threshold_c}°C limit`,
            position: 'insideEndTop',
            color: RED,
            fontFamily: MONO,
          },
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
        itemStyle: { color: WARN, shadowColor: 'rgba(255, 196, 138, 0.7)', shadowBlur: 10 },
        z: 5,
      },
      {
        name: 'Sensor error',
        type: 'scatter',
        data: errs,
        symbol: 'path://M2,2 L8,8 M8,2 L2,8',
        symbolSize: 9,
        itemStyle: { color: MUTED, borderColor: MUTED, borderWidth: 2 },
        tooltip: { valueFormatter: () => 'ERR' },
      },
    ],
  };
}
