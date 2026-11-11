import { DatePipe } from '@angular/common';
import { Component, effect, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar } from '@angular/material/snack-bar';
import { Api, errorMessage } from '../core/api';
import { Auth } from '../core/auth';
import { Branch, UserRow } from '../core/models';
import { TempPasswordDialog } from './temp-password-dialog';

interface Draft {
  username: string;
  full_name: string;
  branch_id: number | null;
  password: string;
}

const EMPTY: Draft = { username: '', full_name: '', branch_id: null, password: '' };

@Component({
  selector: 'app-users',
  imports: [
    DatePipe,
    FormsModule,
    MatButtonModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatSelectModule,
  ],
  templateUrl: './users.html',
  styleUrl: './users.scss',
})
export class UsersPage {
  private readonly api = inject(Api);
  private readonly snack = inject(MatSnackBar);
  private readonly dialog = inject(MatDialog);
  readonly auth = inject(Auth);

  readonly users = signal<UserRow[]>([]);
  readonly branches = signal<Branch[]>([]);
  readonly version = signal(0);
  draft: Draft = { ...EMPTY };

  constructor() {
    this.api.branches().subscribe((b) => this.branches.set(b));
    effect(() => {
      this.version();
      this.api.users().subscribe({
        next: (u) => this.users.set(u),
        error: (e) => this.snack.open(errorMessage(e), 'Dismiss'),
      });
    });
  }

  valid(): boolean {
    const d = this.draft;
    return (
      /^[a-zA-Z0-9._-]{3,64}$/.test(d.username.trim()) &&
      !!d.full_name.trim() &&
      d.branch_id !== null &&
      d.password.length >= 8
    );
  }

  create(): void {
    if (!this.valid()) return;
    const d = this.draft;
    this.api
      .createUser({
        username: d.username.trim(),
        full_name: d.full_name.trim(),
        branch_id: d.branch_id!,
        password: d.password,
      })
      .subscribe({
        next: (u) => {
          this.snack.open(
            `${u.username} created for ${u.branch}. Give them the initial password; they must change it at first sign-in.`,
            'OK',
            { duration: 8000 },
          );
          this.draft = { ...EMPTY };
          this.version.update((v) => v + 1);
        },
        error: (e) => this.snack.open(errorMessage(e), 'Dismiss', { duration: 8000 }),
      });
  }

  setBranch(u: UserRow, branchId: number): void {
    this.patch(u, { branch_id: branchId }, `${u.username} now belongs to the new branch.`);
  }

  setActive(u: UserRow, active: boolean): void {
    this.patch(
      u,
      { is_active: active },
      `${u.username} ${active ? 'reactivated' : 'deactivated'}.`,
    );
  }

  resetPassword(u: UserRow): void {
    this.api.resetPassword(u.id).subscribe({
      next: (r) => {
        this.dialog.open(TempPasswordDialog, {
          data: r,
          width: '440px',
          maxWidth: '95vw',
          disableClose: true,
        });
        this.version.update((v) => v + 1);
      },
      error: (e) => this.snack.open(errorMessage(e), 'Dismiss', { duration: 8000 }),
    });
  }

  private patch(u: UserRow, body: Parameters<Api['updateUser']>[1], done: string): void {
    this.api.updateUser(u.id, body).subscribe({
      next: () => {
        this.snack.open(done, 'OK', { duration: 4000 });
        this.version.update((v) => v + 1);
      },
      error: (e) => this.snack.open(errorMessage(e), 'Dismiss', { duration: 8000 }),
    });
  }
}
