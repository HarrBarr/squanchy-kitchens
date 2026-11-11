import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSnackBar } from '@angular/material/snack-bar';
import { Router } from '@angular/router';
import { errorMessage } from '../core/api';
import { Auth } from '../core/auth';

@Component({
  selector: 'app-change-password',
  imports: [FormsModule, MatButtonModule, MatFormFieldModule, MatInputModule, MatIconModule],
  template: `
    <div class="wrap">
      <form class="panel" (ngSubmit)="submit()">
        <div class="eyebrow">{{ auth.user()?.full_name }}</div>
        <h1>{{ forced() ? 'Choose your own password' : 'Change password' }}</h1>
        @if (forced()) {
          <p class="muted">
            You signed in with a temporary password. Pick a new one (at least 8 characters) before
            continuing.
          </p>
        }
        <mat-form-field appearance="outline">
          <mat-label>Current password</mat-label>
          <input
            matInput
            type="password"
            name="current"
            [(ngModel)]="current"
            autocomplete="current-password"
            required
          />
        </mat-form-field>
        <mat-form-field appearance="outline">
          <mat-label>New password</mat-label>
          <input
            matInput
            type="password"
            name="next"
            [(ngModel)]="next"
            autocomplete="new-password"
            minlength="8"
            required
          />
          <mat-hint>At least 8 characters.</mat-hint>
        </mat-form-field>
        <mat-form-field appearance="outline">
          <mat-label>Repeat new password</mat-label>
          <input
            matInput
            type="password"
            name="repeat"
            [(ngModel)]="repeat"
            autocomplete="new-password"
            required
          />
        </mat-form-field>
        @if (error()) {
          <p class="err" role="alert">{{ error() }}</p>
        }
        <div class="actions">
          @if (!forced()) {
            <button mat-button type="button" (click)="router.navigate(['/'])">Cancel</button>
          } @else {
            <button mat-button type="button" (click)="auth.logout()">Sign out</button>
          }
          <button mat-flat-button class="btn-cta" type="submit">Save password</button>
        </div>
      </form>
    </div>
  `,
  styles: `
    .wrap {
      max-width: 440px;
      margin: 4vh auto 0;
    }
    form {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    h1 {
      font-size: 24px;
      margin-bottom: 8px;
    }
    .err {
      color: var(--sk-red-text);
    }
    .actions {
      display: flex;
      justify-content: flex-end;
      gap: 8px;
      margin-top: 8px;
    }
  `,
})
export class ChangePasswordPage {
  readonly auth = inject(Auth);
  readonly router = inject(Router);
  private readonly snack = inject(MatSnackBar);
  readonly forced = computed(() => !!this.auth.user()?.must_change_password);
  readonly error = signal<string | null>(null);
  current = '';
  next = '';
  repeat = '';

  submit(): void {
    this.error.set(null);
    if (this.next.length < 8)
      return this.error.set('The new password needs at least 8 characters.');
    if (this.next !== this.repeat) return this.error.set('The two new passwords do not match.');
    this.auth.changePassword(this.current, this.next).subscribe({
      next: () => {
        this.snack.open('Password changed.', 'OK', { duration: 4000 });
        this.router.navigate(['/']);
      },
      error: (e) => this.error.set(errorMessage(e)),
    });
  }
}
