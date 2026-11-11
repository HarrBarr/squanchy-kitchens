import { DatePipe } from '@angular/common';
import { Component, computed, effect, inject, input, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar } from '@angular/material/snack-bar';
import { Observable } from 'rxjs';
import { Api, errorMessage } from '../core/api';
import { Auth } from '../core/auth';
import { UploadRecord, UploadStatus } from '../core/models';
import { Refresh } from '../core/refresh';
import { ReasonDialog, ReasonDialogData } from '../shared/reason-dialog';

export const STATUS_LABEL: Record<UploadStatus, string> = {
  active: 'Active',
  flagged_mistake: 'Flagged',
  voided: 'Voided',
};

/** What the signed-in user may do with an upload. The API enforces the same rules. */
export function uploadActions(
  u: Pick<UploadRecord, 'status' | 'uploaded_by_id'>,
  me: { id: number; role: string } | null,
): { flag: boolean; dismiss: boolean; void: boolean } {
  const admin = me?.role === 'admin';
  const own = !!me && u.uploaded_by_id === me.id;
  return {
    flag: u.status !== 'voided' && (admin || own),
    dismiss: admin && u.status === 'flagged_mistake',
    void: admin && u.status !== 'voided',
  };
}

@Component({
  selector: 'app-uploads',
  imports: [
    DatePipe,
    FormsModule,
    MatButtonModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressBarModule,
    MatSelectModule,
  ],
  templateUrl: './uploads.html',
  styleUrl: './uploads.scss',
})
export class UploadsPage {
  private readonly api = inject(Api);
  private readonly dialog = inject(MatDialog);
  private readonly snack = inject(MatSnackBar);
  private readonly refresh = inject(Refresh);
  readonly auth = inject(Auth);

  /** Route data: the admin's pending-review list. */
  readonly review = input(false);
  readonly status = signal<UploadStatus | null>(null);
  readonly logger = signal('');
  readonly rows = signal<UploadRecord[]>([]);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);
  readonly label = STATUS_LABEL;
  readonly me = computed(() => this.auth.user());

  constructor() {
    effect((onCleanup) => {
      this.refresh.version();
      const src: Observable<UploadRecord[]> = this.review()
        ? this.api.pendingReview()
        : this.api.uploads({ status: this.status(), logger: this.logger().trim() || null });
      this.loading.set(true);
      const sub = src.subscribe({
        next: (r) => {
          this.rows.set(r);
          this.loading.set(false);
          this.error.set(null);
        },
        error: (e) => {
          this.error.set(errorMessage(e));
          this.loading.set(false);
        },
      });
      onCleanup(() => sub.unsubscribe());
    });
  }

  actions(u: UploadRecord) {
    return uploadActions(u, this.me());
  }

  private ask(data: ReasonDialogData): Observable<string | undefined> {
    return this.dialog
      .open<ReasonDialog, ReasonDialogData, string>(ReasonDialog, {
        data,
        width: '480px',
        maxWidth: '95vw',
      })
      .afterClosed();
  }

  flag(u: UploadRecord): void {
    this.ask({
      title: 'Flag as uploaded by mistake',
      message: `Summer will review ${u.original_filename}. The data stays on the dashboard until she voids it.`,
      confirm: 'Flag for review',
      initial: u.flag_reason ?? '',
    }).subscribe(
      (reason) => reason && this.run(this.api.flagUpload(u.id, reason), 'Flagged for review.'),
    );
  }

  /** Named voidUpload, not void: in an Angular template `void(u)` is the void operator. */
  voidUpload(u: UploadRecord): void {
    this.ask({
      title: 'Void this upload',
      message: `${u.original_filename} will be hidden from the dashboard, charts and reports, and excursions recomputed without it. The file and its rows are kept for the audit trail.`,
      confirm: 'Void upload',
      danger: true,
      initial: u.flag_reason ?? '',
    }).subscribe(
      (reason) => reason && this.run(this.api.voidUpload(u.id, reason), 'Upload voided.'),
    );
  }

  dismiss(u: UploadRecord): void {
    this.run(this.api.dismissFlag(u.id), 'Flag dismissed: the upload is active again.');
  }

  private run(op: Observable<UploadRecord>, done: string): void {
    op.subscribe({
      next: () => {
        this.snack.open(done, 'OK', { duration: 4000 });
        this.refresh.bump();
      },
      error: (e) => this.snack.open(errorMessage(e), 'Dismiss', { duration: 8000 }),
    });
  }
}
