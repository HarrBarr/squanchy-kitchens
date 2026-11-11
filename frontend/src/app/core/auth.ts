import { Injectable, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { Observable, catchError, firstValueFrom, map, of, switchMap, tap } from 'rxjs';
import { Api } from './api';
import { Me } from './models';

export const TOKEN_KEY = 'sk.token';

function readToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

/**
 * The signed-in user. The token lives in localStorage (acceptable for this demo: it expires,
 * 8 h by default). The API is the real gatekeeper; this only shapes the UI.
 */
@Injectable({ providedIn: 'root' })
export class Auth {
  private readonly api = inject(Api);
  private readonly router = inject(Router);

  private readonly _token = signal<string | null>(readToken());
  readonly user = signal<Me | null>(null);
  readonly isAdmin = computed(() => this.user()?.role === 'admin');
  readonly isSignedIn = computed(() => !!this._token() && !!this.user());

  token(): string | null {
    return this._token();
  }

  /** On app start: if a token is stored, load the user (an expired token signs out). */
  init(): Promise<void> {
    if (!this._token()) return Promise.resolve();
    return firstValueFrom(
      this.api.me().pipe(
        tap((me) => this.user.set(me)),
        map(() => undefined),
        catchError(() => {
          this.clear();
          return of(undefined);
        }),
      ),
    );
  }

  login(username: string, password: string): Observable<Me> {
    return this.api.login(username.trim(), password).pipe(
      tap((t) => this.setToken(t.access_token)),
      switchMap(() => this.api.me()),
      tap((me) => this.user.set(me)),
    );
  }

  changePassword(current: string, next: string): Observable<Me> {
    return this.api.changePassword(current, next).pipe(tap((me) => this.user.set(me)));
  }

  /** Drop the token (stateless JWT: logout is client-side) and go to the sign-in page. */
  logout(): void {
    this.clear();
    this.router.navigate(['/login']);
  }

  clear(): void {
    this.setToken(null);
    this.user.set(null);
  }

  private setToken(token: string | null): void {
    this._token.set(token);
    try {
      if (token) localStorage.setItem(TOKEN_KEY, token);
      else localStorage.removeItem(TOKEN_KEY);
    } catch {
      /* private mode: keep the token in memory only */
    }
  }
}
