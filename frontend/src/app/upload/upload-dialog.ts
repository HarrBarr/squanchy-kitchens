import { DatePipe } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSelectModule } from '@angular/material/select';
import { RouterLink } from '@angular/router';
import { Api, errorMessage } from '../core/api';
import { loggerFromFilename } from '../core/format';
import { ImportSummary, LoggerInfo } from '../core/models';
import { dragHasFiles, isLoggerExport, pickDroppedFile } from './drop';

export interface UploadDialogData {
  /** Files dropped on the page before the dialog opened. */
  files?: ArrayLike<File> | null;
}

@Component({
  selector: 'app-upload-dialog',
  imports: [
    DatePipe,
    RouterLink,
    MatDialogModule,
    MatButtonModule,
    MatFormFieldModule,
    MatSelectModule,
    MatIconModule,
    MatProgressBarModule,
  ],
  templateUrl: './upload-dialog.html',
  styleUrl: './upload-dialog.scss',
})
export class UploadDialog {
  private readonly api = inject(Api);
  private readonly ref = inject(MatDialogRef<UploadDialog, boolean>);
  private readonly data = inject<UploadDialogData | null>(MAT_DIALOG_DATA, { optional: true });

  readonly loggers = signal<LoggerInfo[]>([]);
  readonly file = signal<File | null>(null);
  readonly logger = signal<string | null>(null);
  readonly guessed = signal(false);
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  readonly result = signal<ImportSummary | null>(null);
  readonly notice = signal<string | null>(null);
  readonly dragging = signal(false);
  readonly canSubmit = computed(() => !!this.file() && !!this.logger() && !this.busy());

  private changed = false;

  constructor() {
    this.api.loggers().subscribe({
      next: (l) => {
        this.loggers.set(l);
        this.guessFromFilename();
      },
      error: (e) => this.error.set(errorMessage(e)),
    });
    if (this.data?.files) this.acceptFiles(this.data.files);
  }

  label(l: LoggerInfo): string {
    const c = l.current;
    return c
      ? `${l.logger_code} · ${c.branch} / ${c.fridge} (°${c.unit})`
      : `${l.logger_code} · not assigned`;
  }

  onFile(event: Event): void {
    const input = event.target as HTMLInputElement;
    const f = input.files?.[0] ?? null;
    input.value = ''; // so choosing the same file again still fires (change)
    if (f && !isLoggerExport(f)) {
      this.acceptFiles([f]);
      return;
    }
    this.setFile(f);
  }

  setFile(f: File | null): void {
    this.file.set(f);
    this.result.set(null);
    this.error.set(null);
    this.notice.set(null);
    this.guessFromFilename();
  }

  /** Files from a drop (on the zone, the dialog, or the page). */
  acceptFiles(files: ArrayLike<File>): void {
    if (this.busy()) return;
    const pick = pickDroppedFile(files);
    if (pick.file) this.setFile(pick.file);
    this.notice.set(pick.notice);
  }

  // Drag and drop on the drop zone. stopPropagation keeps the page-level drop handler
  // from also seeing the drop.
  onDragOver(e: DragEvent): void {
    if (!dragHasFiles(e) || this.busy()) return;
    e.preventDefault();
    e.stopPropagation();
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy';
    this.dragging.set(true);
  }

  onDragLeave(e: DragEvent): void {
    const zone = e.currentTarget as HTMLElement | null;
    if (zone && e.relatedTarget instanceof Node && zone.contains(e.relatedTarget)) return;
    this.dragging.set(false);
  }

  onDrop(e: DragEvent): void {
    e.preventDefault();
    e.stopPropagation();
    this.dragging.set(false);
    if (this.result()) this.another();
    this.acceptFiles(e.dataTransfer?.files ?? []);
  }

  selectLogger(code: string | null): void {
    this.logger.set(code);
    this.guessed.set(false);
  }

  private guessFromFilename(): void {
    const f = this.file();
    if (!f) return;
    const code = loggerFromFilename(
      f.name,
      this.loggers().map((l) => l.logger_code),
    );
    if (code) {
      this.logger.set(code);
      this.guessed.set(true);
    }
  }

  submit(): void {
    const f = this.file();
    const code = this.logger();
    if (!f || !code) return;
    this.busy.set(true);
    this.error.set(null);
    this.api.upload(f, code).subscribe({
      next: (r) => {
        this.result.set(r);
        this.busy.set(false);
        this.changed ||= !r.already_imported;
      },
      error: (e) => {
        this.error.set(errorMessage(e));
        this.busy.set(false);
      },
    });
  }

  another(): void {
    this.file.set(null);
    this.logger.set(null);
    this.result.set(null);
    this.notice.set(null);
  }

  close(): void {
    this.ref.close(this.changed);
  }
}
