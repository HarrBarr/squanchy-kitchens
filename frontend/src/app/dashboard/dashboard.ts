import { DatePipe } from '@angular/common';
import { Component, computed, effect, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSelectModule } from '@angular/material/select';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { Api, errorMessage } from '../core/api';
import { addDays, COLOUR_LABEL, colourFor, fmtTemp } from '../core/format';
import { Branch, Dashboard } from '../core/models';
import { Refresh } from '../core/refresh';
import { UploadLauncher } from '../upload/upload-launcher';

@Component({
  selector: 'app-dashboard',
  imports: [
    DatePipe,
    RouterLink,
    MatButtonModule,
    MatIconModule,
    MatFormFieldModule,
    MatSelectModule,
    MatProgressBarModule,
  ],
  templateUrl: './dashboard.html',
  styleUrl: './dashboard.scss',
})
export class DashboardPage {
  private readonly api = inject(Api);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly launcher = inject(UploadLauncher);
  private readonly refresh = inject(Refresh);

  private readonly query = toSignal(this.route.queryParamMap, { requireSync: true });
  readonly from = computed(() => this.query().get('from'));
  readonly to = computed(() => this.query().get('to'));
  readonly branch = computed(() => this.query().get('branch'));

  readonly data = signal<Dashboard | null>(null);
  readonly branches = signal<Branch[]>([]);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);
  readonly hasReadings = computed(() =>
    (this.data()?.fridges ?? []).some((f) => f.last_reading_local),
  );

  readonly colourFor = colourFor;
  readonly label = COLOUR_LABEL;
  readonly fmtTemp = fmtTemp;

  constructor() {
    this.api.branches().subscribe({ next: (b) => this.branches.set(b), error: () => undefined });
    effect((onCleanup) => {
      this.refresh.version();
      const period = { from: this.from(), to: this.to() };
      const branch = this.branch();
      this.loading.set(true);
      this.error.set(null);
      const sub = this.api.dashboard(period, branch).subscribe({
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
    this.navigate({ from: addDays(d.period_from, days), to: addDays(d.period_to, days) });
  }

  latest(): void {
    this.navigate({ from: null, to: null });
  }

  setBranch(branch: string | null): void {
    this.navigate({ branch });
  }

  private navigate(params: Record<string, string | null>): void {
    this.router.navigate([], { queryParams: params, queryParamsHandling: 'merge' });
  }

  detailParams(): Record<string, string> {
    const d = this.data();
    return d ? { from: d.period_from, to: d.period_to } : {};
  }

  upload(): void {
    this.launcher.open();
  }
}
