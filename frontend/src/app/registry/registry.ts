import { DatePipe } from '@angular/common';
import { Component, computed, effect, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatAutocompleteModule } from '@angular/material/autocomplete';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar } from '@angular/material/snack-bar';
import { Api, errorMessage } from '../core/api';
import { LoggerInfo, UploadRecord } from '../core/models';
import { Refresh } from '../core/refresh';

interface Draft {
  code: string;
  branch: string;
  fridge: string;
  unit: 'C' | 'F';
  assigned_from: string;
}

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

@Component({
  selector: 'app-registry',
  imports: [
    DatePipe,
    FormsModule,
    MatAutocompleteModule,
    MatButtonModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatSelectModule,
  ],
  templateUrl: './registry.html',
  styleUrl: './registry.scss',
})
export class RegistryPage {
  private readonly api = inject(Api);
  private readonly snack = inject(MatSnackBar);
  private readonly refresh = inject(Refresh);

  readonly loggers = signal<LoggerInfo[]>([]);
  readonly uploads = signal<UploadRecord[]>([]);
  readonly error = signal<string | null>(null);
  readonly busy = signal(false);
  draft: Draft = { code: '', branch: '', fridge: '', unit: 'C', assigned_from: today() };

  readonly branchNames = computed(() =>
    [...new Set(this.loggers().flatMap((l) => l.assignments.map((a) => a.branch)))].sort(),
  );
  readonly fridgeNames = computed(() =>
    [...new Set(this.loggers().flatMap((l) => l.assignments.map((a) => a.fridge)))].sort(),
  );

  constructor() {
    effect(() => {
      this.refresh.version();
      this.load();
    });
  }

  load(): void {
    this.api.loggers().subscribe({
      next: (l) => this.loggers.set(l),
      error: (e) => this.error.set(errorMessage(e)),
    });
    this.api.uploads().subscribe({ next: (u) => this.uploads.set(u), error: () => undefined });
  }

  /** Earlier assignments (moves), for the History column. */
  history(l: LoggerInfo) {
    return l.assignments.filter((a) => a.assigned_to);
  }

  move(l: LoggerInfo): void {
    this.draft = {
      code: l.logger_code,
      branch: l.current?.branch ?? '',
      fridge: '',
      unit: l.current?.unit ?? 'C',
      assigned_from: today(),
    };
    document.getElementById('assign-form')?.scrollIntoView({ behavior: 'smooth' });
  }

  valid(): boolean {
    const d = this.draft;
    return (
      /^TL-\d{3,6}$/i.test(d.code.trim()) &&
      !!d.branch.trim() &&
      !!d.fridge.trim() &&
      !!d.assigned_from
    );
  }

  save(): void {
    if (!this.valid()) return;
    const d = this.draft;
    this.busy.set(true);
    this.api
      .addAssignment(d.code.trim().toUpperCase(), {
        branch: d.branch.trim(),
        fridge: d.fridge.trim(),
        unit: d.unit,
        assigned_from: d.assigned_from,
      })
      .subscribe({
        next: (l) => {
          this.busy.set(false);
          this.snack.open(
            `${l.logger_code} is now in ${l.current?.branch} / ${l.current?.fridge} from ${d.assigned_from}.`,
            'OK',
            { duration: 5000 },
          );
          this.draft = { code: '', branch: '', fridge: '', unit: 'C', assigned_from: today() };
          this.refresh.bump();
        },
        error: (e) => {
          this.busy.set(false);
          this.snack.open(errorMessage(e), 'Dismiss', { duration: 8000 });
        },
      });
  }
}
