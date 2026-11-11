import { DatePipe, JsonPipe } from '@angular/common';
import { Component, effect, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { Api, errorMessage } from '../core/api';
import { AuditEntry } from '../core/models';

@Component({
  selector: 'app-audit',
  imports: [
    DatePipe,
    JsonPipe,
    FormsModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatSelectModule,
  ],
  template: `
    <div class="page-head">
      <div>
        <div class="eyebrow">Admin</div>
        <h1>Audit <span class="aurora-text">log</span></h1>
        <div class="sub">
          Who uploaded, flagged, voided, exported or changed an account, and when (UTC).
        </div>
      </div>
    </div>
    <div class="toolbar-row">
      <mat-form-field appearance="outline" subscriptSizing="dynamic" class="half">
        <mat-label>Action</mat-label>
        <mat-select [value]="action()" (valueChange)="action.set($event)">
          <mat-option [value]="null">All</mat-option>
          <mat-option value="upload.">Uploads (all)</mat-option>
          <mat-option value="upload.voided">Voids</mat-option>
          <mat-option value="upload.flagged">Flags</mat-option>
          <mat-option value="report.exported">Report exports</mat-option>
          <mat-option value="user.">Users (all)</mat-option>
          <mat-option value="registry.assignment_created">Registry changes</mat-option>
        </mat-select>
      </mat-form-field>
      <mat-form-field appearance="outline" subscriptSizing="dynamic" class="half">
        <mat-label>Username</mat-label>
        <input
          matInput
          [ngModel]="user()"
          (ngModelChange)="user.set($event)"
          placeholder="manager.haifa"
        />
      </mat-form-field>
    </div>
    @if (error()) {
      <div class="state error">
        <mat-icon>error</mat-icon>
        <p>{{ error() }}</p>
      </div>
    }
    <section class="panel">
      <div class="table-wrap">
        <table class="data stack">
          <thead>
            <tr>
              <th>When</th>
              <th>Who</th>
              <th>Action</th>
              <th>Details</th>
            </tr>
          </thead>
          <tbody>
            @for (e of rows(); track e.id) {
              <tr>
                <td data-label="When" class="mono">
                  {{ e.created_at | date: 'd MMM yyyy HH:mm:ss' }}
                </td>
                <td data-label="Who">
                  {{ e.user ?? 'system' }} <span class="muted mono small">{{ e.username }}</span>
                </td>
                <td data-label="Action">
                  <span class="mono action">{{ e.action }}</span>
                </td>
                <td data-label="Details" class="details mono">{{ e.details | json }}</td>
              </tr>
            } @empty {
              <tr>
                <td class="muted">No entries.</td>
              </tr>
            }
          </tbody>
        </table>
      </div>
    </section>
  `,
  styles: `
    .action {
      color: var(--sk-accent);
    }
    .small {
      font-size: 11px;
    }
    td.details {
      white-space: pre-wrap;
      word-break: break-word;
      font-size: 11px;
      color: var(--sk-muted);
      max-width: 520px;
    }
  `,
})
export class AuditPage {
  private readonly api = inject(Api);
  readonly action = signal<string | null>(null);
  readonly user = signal('');
  readonly rows = signal<AuditEntry[]>([]);
  readonly error = signal<string | null>(null);

  constructor() {
    effect((onCleanup) => {
      const sub = this.api
        .auditLog({ action: this.action(), user: this.user().trim() || null })
        .subscribe({
          next: (r) => this.rows.set(r),
          error: (e) => this.error.set(errorMessage(e)),
        });
      onCleanup(() => sub.unsubscribe());
    });
  }
}
