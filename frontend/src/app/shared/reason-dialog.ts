import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';

export interface ReasonDialogData {
  title: string;
  message: string;
  confirm: string;
  danger?: boolean;
  initial?: string;
}

/** Asks for a short reason (flag, void). Closes with the reason, or undefined on cancel. */
@Component({
  selector: 'app-reason-dialog',
  imports: [FormsModule, MatDialogModule, MatButtonModule, MatFormFieldModule, MatInputModule],
  template: `
    <h2 mat-dialog-title>{{ data.title }}</h2>
    <mat-dialog-content>
      <p class="muted">{{ data.message }}</p>
      <mat-form-field appearance="outline" class="full">
        <mat-label>Reason</mat-label>
        <textarea
          matInput
          rows="3"
          [ngModel]="reason()"
          (ngModelChange)="reason.set($event)"
          maxlength="1000"
          data-testid="reason"
        ></textarea>
        <mat-hint>At least 3 characters. Saved in the audit log.</mat-hint>
      </mat-form-field>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button mat-dialog-close>Cancel</button>
      <button
        mat-flat-button
        [class.btn-cta]="!data.danger"
        [class.btn-danger]="data.danger"
        [disabled]="reason().trim().length < 3"
        (click)="ref.close(reason().trim())"
      >
        {{ data.confirm }}
      </button>
    </mat-dialog-actions>
  `,
  styles: `
    .full {
      width: 100%;
    }
  `,
})
export class ReasonDialog {
  readonly data = inject<ReasonDialogData>(MAT_DIALOG_DATA);
  readonly ref = inject(MatDialogRef<ReasonDialog, string>);
  readonly reason = signal(this.data.initial ?? '');
}
