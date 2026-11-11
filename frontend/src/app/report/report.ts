import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, computed, effect, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSelectModule } from '@angular/material/select';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { Api, errorMessage, reportCsvUrl } from '../core/api';
import { Branch, Report } from '../core/models';
import { Refresh } from '../core/refresh';

@Component({
  selector: 'app-report',
  imports: [
    DatePipe,
    DecimalPipe,
    RouterLink,
    MatButtonModule,
    MatIconModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatProgressBarModule,
  ],
  templateUrl: './report.html',
  styleUrl: './report.scss',
})
export class ReportPage {
  private readonly api = inject(Api);
  private readonly router = inject(Router);
  private readonly refresh = inject(Refresh);
  private readonly query = toSignal(inject(ActivatedRoute).queryParamMap, { requireSync: true });

  readonly branch = computed(() => this.query().get('branch'));
  readonly data = signal<Report | null>(null);
  readonly branches = signal<Branch[]>([]);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);
  readonly csvUrl = computed(() => {
    const d = this.data();
    return d ? reportCsvUrl({ from: d.period_from, to: d.period_to }, this.branch()) : '#';
  });

  constructor() {
    this.api.branches().subscribe({ next: (b) => this.branches.set(b), error: () => undefined });
    effect((onCleanup) => {
      this.refresh.version();
      const q = this.query();
      this.loading.set(true);
      this.error.set(null);
      const sub = this.api
        .report({ from: q.get('from'), to: q.get('to') }, q.get('branch'))
        .subscribe({
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

  set(params: Record<string, string | null>): void {
    const d = this.data();
    const base = d ? { from: d.period_from, to: d.period_to } : {};
    this.router.navigate([], { queryParams: { ...base, branch: this.branch(), ...params } });
  }

  print(): void {
    window.print();
  }
}
