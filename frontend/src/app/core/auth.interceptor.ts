import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, throwError } from 'rxjs';
import { Auth } from './auth';

const LOGIN_URL = '/api/auth/login';

/**
 * Adds `Authorization: Bearer <token>` to /api calls (not to login). A 401 means the session
 * is over: drop the token and go to sign-in. A 403 "must_change_password" goes to the
 * change-password screen.
 */
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(Auth);
  const router = inject(Router);
  const token = auth.token();
  const isApi = req.url.startsWith('/api/');
  const isLogin = req.url.startsWith(LOGIN_URL);
  const authed =
    isApi && !isLogin && token
      ? req.clone({ setHeaders: { Authorization: `Bearer ${token}` } })
      : req;

  return next(authed).pipe(
    catchError((err: unknown) => {
      if (err instanceof HttpErrorResponse && isApi && !isLogin) {
        if (err.status === 401) {
          auth.clear();
          const returnUrl = router.url.startsWith('/login') ? undefined : router.url;
          router.navigate(['/login'], { queryParams: returnUrl ? { returnUrl } : {} });
        } else if (err.status === 403 && err.error?.detail?.code === 'must_change_password') {
          router.navigate(['/change-password']);
        }
      }
      return throwError(() => err);
    }),
  );
};
