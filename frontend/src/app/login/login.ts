import { Component, inject, input, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { Router } from '@angular/router';
import { errorMessage } from '../core/api';
import { Auth } from '../core/auth';

@Component({
  selector: 'app-login',
  imports: [
    FormsModule,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    MatIconModule,
    MatProgressBarModule,
  ],
  templateUrl: './login.html',
  styleUrl: './login.scss',
})
export class LoginPage {
  private readonly auth = inject(Auth);
  private readonly router = inject(Router);

  /** Where to go after signing in (from the guard / interceptor). */
  readonly returnUrl = input<string>();
  username = '';
  password = '';
  readonly hide = signal(true);
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);

  submit(): void {
    if (!this.username.trim() || !this.password || this.busy()) return;
    this.busy.set(true);
    this.error.set(null);
    this.auth.login(this.username, this.password).subscribe({
      next: (me) => {
        this.busy.set(false);
        if (me.must_change_password) this.router.navigate(['/change-password']);
        else this.router.navigateByUrl(this.returnUrl() || '/');
      },
      error: (e) => {
        this.busy.set(false);
        this.error.set(errorMessage(e));
      },
    });
  }
}
