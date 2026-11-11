import { Component, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MAT_DIALOG_DATA, MatDialogModule } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { PasswordReset } from '../core/models';

/** Shows a reset password exactly once. It is not e-mailed and cannot be shown again. */
@Component({
  selector: 'app-temp-password-dialog',
  imports: [MatDialogModule, MatButtonModule, MatIconModule],
  template: `
    <h2 mat-dialog-title>Temporary password</h2>
    <mat-dialog-content>
      <p>
        Give this to <strong>{{ data.user.full_name }}</strong> ({{ data.user.username }}). They
        will be asked to choose their own password when they sign in.
      </p>
      <div class="pw mono" data-testid="temp-password">{{ data.temporary_password }}</div>
      <p class="muted small">
        This is shown only once. It is not e-mailed or stored in plain text.
      </p>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button (click)="copy()">
        <mat-icon>{{ copied() ? 'check' : 'content_copy' }}</mat-icon>
        {{ copied() ? 'Copied' : 'Copy' }}
      </button>
      <button mat-flat-button class="btn-cta" mat-dialog-close>Done</button>
    </mat-dialog-actions>
  `,
  styles: `
    .pw {
      font-size: 22px;
      padding: 14px 16px;
      border-radius: 14px;
      text-align: center;
      letter-spacing: 0.06em;
      background: rgba(124, 242, 200, 0.08);
      border: 1px solid rgba(124, 242, 200, 0.35);
      color: var(--sk-accent);
      user-select: all;
    }
    .small {
      font-size: 12px;
    }
  `,
})
export class TempPasswordDialog {
  readonly data = inject<PasswordReset>(MAT_DIALOG_DATA);
  readonly copied = signal(false);

  copy(): void {
    navigator.clipboard?.writeText(this.data.temporary_password).then(() => this.copied.set(true));
  }
}
