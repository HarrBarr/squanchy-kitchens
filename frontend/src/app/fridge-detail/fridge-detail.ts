import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, computed, effect, inject, input, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { NgxEchartsDirective } from 'ngx-echarts';
import { Api, errorMessage, reportCsvUrl } from '../core/api';
import { addDays, fmtDuration } from '../core/format';
import { Series } from '../core/models';
import { Refresh } from '../core/refresh';
import { buildChartOptions } from './chart-options';

@Component({
  selector: 'app-fridge-detail',
  imports: [
    DatePipe,
    DecimalPipe,
    RouterLink,
    MatButtonModule,
    MatIconModule,
    MatProgressBarModule,
    NgxEchartsDirective,
  ],
  templateUrl: './fridge-detail.html',
  styleUrl: './fridge-detail.scss',
})
export class FridgeDetailPage {
  private readonly api = inject(Api);
  private readonly router = inject(Router);
  private readonly refresh = inject(Refresh);
  private readonly query = toSignal(inject(ActivatedRoute).queryParamMap, { requireSync: true });

  /** Route param, bound by withComponentInputBinding(). */
  readonly id = input.required<string>();

  readonly data = signal<Series | null>(null);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);
  readonly options = computed(() => {
    const d = this.data();
    return d ? buildChartOptions(d) : null;
  });
  readonly errCount = computed(
    () => this.data()?.readings.filter((r) => r.status === 'err').length ?? 0,
  );
  readonly loggers = computed(() => [...new Set(this.data()?.readings.map((r) => r.logger) ?? [])]);
  readonly fmtDuration = fmtDuration;

  constructor() {
    effect((onCleanup) => {
      this.refresh.version();
      const id = Number(this.id());
      const q = this.query();
      this.loading.set(true);
      this.error.set(null);
      const sub = this.api.series(id, { from: q.get('from'), to: q.get('to') }).subscribe({
        next: (d) => {
          this.data.set(d);
          this.loading.set(false);
        },
        error: (e) => {
          this.error.set(errorMessage(e));
          this.loading.set(false);
        },
      });
      onCleanup(() => sub.unsubscribe());
    });
  }

  shiftWeek(days: number): void {
    const d = this.data();
    if (!d) return;
    this.router.navigate([], {
      queryParams: { from: addDays(d.period_from, days), to: addDays(d.period_to, days) },
    });
  }

  periodParams(): Record<string, string> {
    const d = this.data();
    return d ? { from: d.period_from, to: d.period_to } : {};
  }

  csvUrl(): string {
    const d = this.data();
    return d ? reportCsvUrl({ from: d.period_from, to: d.period_to }, null, d.fridge_id) : '#';
  }
}
